# app/routers/companies.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from uuid import UUID
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.auth.dependencies import get_current_user, verify_csrf
from app.schemas.companies import (
    CompanyCreate, 
    CompanyUpdate, 
    CompanyResponse,
    CompanySearchResponse
)
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/companies",
    tags=["companies"]
)


# ============================================================================
# PUBLIC ENDPOINTS - No authentication required
# ============================================================================

@router.get(
    "/search",
    response_model=List[CompanySearchResponse],
    summary="Search companies (Public)",
    description="Full-text search across companies using materialized view with language support"
)
async def search_companies(
    q: str = Query(..., min_length=1, description="Search query"),
    lang: str = Query("es", regex="^(es|en)$", description="Language for search (es/en)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: asyncpg.Connection = Depends(get_db)
):
    """
    Search companies using PostgreSQL full-text search with GIN index.
    Searches across company name, description, product, commune, and user info.
    """
    try:
        search_query = """
            SELECT 
                company_id,
                company_name,
                company_description_es,
                company_description_en,
                address,
                company_email,
                product_name_es,
                product_name_en,
                user_name,
                user_email,
                commune_name,
                ts_rank(search_vector, query) AS rank
            FROM fastapi.company_search,
                 to_tsquery($1, $2) query
            WHERE search_vector @@ query
            ORDER BY rank DESC
            LIMIT $3 OFFSET $4
        """
        
        lang_config = 'spanish' if lang == 'es' else 'english'
        formatted_query = ' & '.join(q.split())
        
        rows = await db.fetch(
            search_query,
            lang_config,
            formatted_query,
            limit,
            offset
        )
        
        results = []
        for row in rows:
            results.append(CompanySearchResponse(
                uuid=row["company_id"],
                name=row["company_name"],
                description=row[f"company_description_{lang}"],
                address=row["address"],
                email=row["company_email"],
                product_name=row[f"product_name_{lang}"],
                commune_name=row["commune_name"],
                relevance_score=float(row["rank"])
            ))
        
        logger.info(
            "company_search_performed",
            query=q,
            lang=lang,
            results_count=len(results)
        )
        
        return results
        
    except Exception as e:
        logger.error("company_search_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search companies"
        )


@router.get(
    "/{company_uuid}",
    response_model=CompanyResponse,
    summary="Get company by UUID (Public)",
    description="Retrieve detailed information about a specific company"
)
async def get_company(
    company_uuid: UUID,
    db: asyncpg.Connection = Depends(get_db)
):
    """Get a single company by UUID - public endpoint"""
    try:
        company = await DB.get_company_by_uuid(conn=db, company_uuid=company_uuid)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with UUID {company_uuid} not found"
            )
        return CompanyResponse(**company)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_company_error", company_uuid=str(company_uuid), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve company"
        )


@router.get(
    "/",
    response_model=List[CompanyResponse],
    summary="List all companies (Public)",
    description="Retrieve a paginated list of all companies"
)
async def list_companies(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: asyncpg.Connection = Depends(get_db)
):
    """List all companies with pagination - public endpoint"""
    try:
        companies = await DB.get_all_companies(conn=db, limit=limit, offset=offset)
        return [CompanyResponse(**company) for company in companies]
    except Exception as e:
        logger.error("list_companies_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve companies"
        )


# ============================================================================
# AUTHENTICATED ENDPOINTS - Requires login
# ============================================================================

@router.post(
    "/",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new company (Authenticated)",
    description="Create a new company - requires authentication"
)
async def create_company(
    company_data: CompanyCreate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Create a new company - authenticated users only"""
    try:
        user_uuid = UUID(current_user["sub"])
        
        company = await DB.create_company(
            conn=db,
            user_uuid=user_uuid,
            product_uuid=company_data.product_uuid,
            commune_uuid=company_data.commune_uuid,
            name=company_data.name,
            description_es=company_data.description_es,
            description_en=company_data.description_en,
            address=company_data.address,
            phone=company_data.phone,
            email=company_data.email,
            image_url=company_data.image_url
        )
        
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "company_created",
            company_uuid=str(company["uuid"]),
            user_uuid=str(user_uuid)
        )
        
        return CompanyResponse(**company)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("create_company_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create company"
        )


@router.put(
    "/{company_uuid}",
    response_model=CompanyResponse,
    summary="Update a company (Authenticated)",
    description="Update a company - only owner can update"
)
async def update_company(
    company_uuid: UUID,
    company_data: CompanyUpdate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Update a company - only the owner can update"""
    try:
        user_uuid = UUID(current_user["sub"])
        
        company = await DB.update_company_by_uuid(
            conn=db,
            company_uuid=company_uuid,
            user_uuid=user_uuid,
            name=company_data.name,
            description_es=company_data.description_es,
            description_en=company_data.description_en,
            address=company_data.address,
            phone=company_data.phone,
            email=company_data.email,
            image_url=company_data.image_url,
            product_uuid=company_data.product_uuid,
            commune_uuid=company_data.commune_uuid
        )
        
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "company_updated",
            company_uuid=str(company_uuid),
            user_uuid=str(user_uuid)
        )
        
        return CompanyResponse(**company)
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("update_company_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update company"
        )


@router.delete(
    "/{company_uuid}",
    status_code=status.HTTP_200_OK,
    summary="Delete a company (Authenticated)",
    description="Delete a company - only owner can delete"
)
async def delete_company(
    company_uuid: UUID,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Delete a company - only the owner can delete"""
    try:
        user_uuid = UUID(current_user["sub"])
        
        result = await DB.delete_company_by_uuid(
            conn=db,
            company_uuid=company_uuid,
            user_uuid=user_uuid
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found or you don't have permission to delete it"
            )
        
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        return {"message": "Company successfully deleted", "uuid": str(company_uuid)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_company_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete company"
        )


@router.get(
    "/user/my-companies",
    response_model=List[CompanyResponse],
    summary="Get current user's companies (Authenticated)",
    description="Retrieve all companies owned by the current user"
)
async def get_my_companies(
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Get all companies owned by the current user"""
    try:
        user_uuid = UUID(current_user["sub"])
        
        companies = await DB.get_companies_by_user_uuid(conn=db, user_uuid=user_uuid)
        return [CompanyResponse(**company) for company in companies]
        
    except Exception as e:
        logger.error("get_my_companies_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve your companies"
        )