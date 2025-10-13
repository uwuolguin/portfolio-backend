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
        # Build the search query based on language
        # The materialized view has separate tsvectors for Spanish and English
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
        
        # Determine language config for to_tsquery
        lang_config = 'spanish' if lang == 'es' else 'english'
        
        # Format search terms for tsquery (replace spaces with & for AND search)
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
        query = """
            SELECT 
                c.uuid,
                c.user_uuid,
                c.product_uuid,
                c.commune_uuid,
                c.name,
                c.description_es,
                c.description_en,
                c.address,
                c.phone,
                c.email,
                c.image_url,
                c.created_at,
                c.updated_at,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            WHERE c.uuid = $1
        """
        
        row = await db.fetchrow(query, company_uuid)
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with UUID {company_uuid} not found"
            )
        
        return CompanyResponse(**dict(row))
        
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
        query = """
            SELECT 
                c.uuid,
                c.user_uuid,
                c.product_uuid,
                c.commune_uuid,
                c.name,
                c.description_es,
                c.description_en,
                c.address,
                c.phone,
                c.email,
                c.image_url,
                c.created_at,
                c.updated_at,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            ORDER BY c.created_at DESC
            LIMIT $1 OFFSET $2
        """
        
        rows = await db.fetch(query, limit, offset)
        return [CompanyResponse(**dict(row)) for row in rows]
        
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
        
        # Verify that product and commune exist
        product_exists = await db.fetchval(
            "SELECT 1 FROM fastapi.products WHERE uuid = $1",
            company_data.product_uuid
        )
        if not product_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with UUID {company_data.product_uuid} does not exist"
            )
        
        commune_exists = await db.fetchval(
            "SELECT 1 FROM fastapi.communes WHERE uuid = $1",
            company_data.commune_uuid
        )
        if not commune_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Commune with UUID {company_data.commune_uuid} does not exist"
            )
        
        # Insert company
        insert_query = """
            INSERT INTO fastapi.companies 
                (user_uuid, product_uuid, commune_uuid, name, description_es, 
                 description_en, address, phone, email, image_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING uuid, user_uuid, product_uuid, commune_uuid, name, 
                      description_es, description_en, address, phone, email, 
                      image_url, created_at, updated_at
        """
        
        row = await db.fetchrow(
            insert_query,
            user_uuid,
            company_data.product_uuid,
            company_data.commune_uuid,
            company_data.name,
            company_data.description_es,
            company_data.description_en,
            company_data.address,
            company_data.phone,
            company_data.email,
            company_data.image_url
        )
        
        # Refresh materialized view
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "company_created",
            company_uuid=str(row["uuid"]),
            user_uuid=str(user_uuid)
        )
        
        # Fetch complete data with joins
        complete_data = await db.fetchrow("""
            SELECT 
                c.*,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            WHERE c.uuid = $1
        """, row["uuid"])
        
        return CompanyResponse(**dict(complete_data))
        
    except HTTPException:
        raise
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
        
        # Verify ownership
        owner_check = await db.fetchval(
            "SELECT user_uuid FROM fastapi.companies WHERE uuid = $1",
            company_uuid
        )
        
        if not owner_check:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with UUID {company_uuid} not found"
            )
        
        if owner_check != user_uuid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own companies"
            )
        
        # Build update query dynamically for only provided fields
        update_fields = []
        params = []
        param_count = 1
        
        if company_data.name is not None:
            update_fields.append(f"name = ${param_count}")
            params.append(company_data.name)
            param_count += 1
        
        if company_data.description_es is not None:
            update_fields.append(f"description_es = ${param_count}")
            params.append(company_data.description_es)
            param_count += 1
        
        if company_data.description_en is not None:
            update_fields.append(f"description_en = ${param_count}")
            params.append(company_data.description_en)
            param_count += 1
        
        if company_data.address is not None:
            update_fields.append(f"address = ${param_count}")
            params.append(company_data.address)
            param_count += 1
        
        if company_data.phone is not None:
            update_fields.append(f"phone = ${param_count}")
            params.append(company_data.phone)
            param_count += 1
        
        if company_data.email is not None:
            update_fields.append(f"email = ${param_count}")
            params.append(company_data.email)
            param_count += 1
        
        if company_data.image_url is not None:
            update_fields.append(f"image_url = ${param_count}")
            params.append(company_data.image_url)
            param_count += 1
        
        if company_data.product_uuid is not None:
            # Verify product exists
            product_exists = await db.fetchval(
                "SELECT 1 FROM fastapi.products WHERE uuid = $1",
                company_data.product_uuid
            )
            if not product_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Product with UUID {company_data.product_uuid} does not exist"
                )
            update_fields.append(f"product_uuid = ${param_count}")
            params.append(company_data.product_uuid)
            param_count += 1
        
        if company_data.commune_uuid is not None:
            # Verify commune exists
            commune_exists = await db.fetchval(
                "SELECT 1 FROM fastapi.communes WHERE uuid = $1",
                company_data.commune_uuid
            )
            if not commune_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Commune with UUID {company_data.commune_uuid} does not exist"
                )
            update_fields.append(f"commune_uuid = ${param_count}")
            params.append(company_data.commune_uuid)
            param_count += 1
        
        if not update_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update"
            )
        
        # Add updated_at
        update_fields.append(f"updated_at = NOW()")
        
        # Add company_uuid as final parameter
        params.append(company_uuid)
        
        update_query = f"""
            UPDATE fastapi.companies
            SET {', '.join(update_fields)}
            WHERE uuid = ${param_count}
            RETURNING uuid
        """
        
        await db.execute(update_query, *params)
        
        # Refresh materialized view
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "company_updated",
            company_uuid=str(company_uuid),
            user_uuid=str(user_uuid)
        )
        
        # Fetch updated company
        updated_company = await db.fetchrow("""
            SELECT 
                c.*,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            WHERE c.uuid = $1
        """, company_uuid)
        
        return CompanyResponse(**dict(updated_company))
        
    except HTTPException:
        raise
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
        
        # Refresh materialized view
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
        
        query = """
            SELECT 
                c.*,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            WHERE c.user_uuid = $1
            ORDER BY c.created_at DESC
        """
        
        rows = await db.fetch(query, user_uuid)
        return [CompanyResponse(**dict(row)) for row in rows]
        
    except Exception as e:
        logger.error("get_my_companies_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve your companies"
        )