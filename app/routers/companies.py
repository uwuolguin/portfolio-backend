# app/routers/companies.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from uuid import UUID
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.auth.dependencies import get_current_user, verify_csrf
from app.schemas.companies import CompanyCreate, CompanyUpdate, CompanyResponse, CompanySearchResponse
from app.utils.translator import translate_field
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/companies", tags=["companies"])

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
    """Search companies using PostgreSQL full-text search with GIN index."""
    try:
        results = await DB.search_companies(
            conn=db,
            query=q,
            lang=lang,
            limit=limit,
            offset=offset
        )

        # Translate fields dynamically for response
        translated_results = []
        for result in results:
            translated_results.append({
                **result,
                "name": translate_field(result["name"], lang),
                "description": translate_field(result["description"], lang),
                "product_name": translate_field(result["product_name"], lang)
            })

        logger.info(
            "company_search_performed",
            query=q,
            lang=lang,
            results_count=len(translated_results)
        )

        return [CompanySearchResponse(**res) for res in translated_results]

    except Exception as e:
        logger.error("company_search_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search companies"
        )

# ============================================================================
# AUTHENTICATED ENDPOINTS - Requires login
# ============================================================================

@router.post(
    "/",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new company (Authenticated)",
    description="Create a new company - requires authentication. Each user can only create ONE company."
)
async def create_company(
    company_data: CompanyCreate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Create a new company - authenticated users only."""
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


        # Translate fields
        company["name"] = translate_field(company["name"], company_data.lang if hasattr(company_data, "lang") else "es")
        company["description"] = translate_field(
            company["description_es"] if company_data.lang == "es" else company["description_en"],
            company_data.lang if hasattr(company_data, "lang") else "es"
        )
        company["product_name"] = translate_field(
            company["product_name_es"] if company_data.lang == "es" else company["product_name_en"],
            company_data.lang if hasattr(company_data, "lang") else "es"
        )

        logger.info("company_created", company_uuid=str(company["uuid"]), user_uuid=str(user_uuid))
        return CompanyResponse(**company)

    except ValueError as e:
        if "already have a company" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("create_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create company")

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


        # Translate fields
        company["name"] = translate_field(company["name"], company_data.lang if hasattr(company_data, "lang") else "es")
        company["description"] = translate_field(
            company["description_es"] if company_data.lang == "es" else company["description_en"],
            company_data.lang if hasattr(company_data, "lang") else "es"
        )
        company["product_name"] = translate_field(
            company["product_name_es"] if company_data.lang == "es" else company["product_name_en"],
            company_data.lang if hasattr(company_data, "lang") else "es"
        )

        logger.info("company_updated", company_uuid=str(company_uuid), user_uuid=str(user_uuid))
        return CompanyResponse(**company)

    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("update_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update company")

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
        result = await DB.delete_company_by_uuid(conn=db, company_uuid=company_uuid, user_uuid=user_uuid)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found or you don't have permission to delete it"
            )

        return {"message": "Company successfully deleted", "uuid": str(company_uuid)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete company")


@router.get(
    "/user/my-company",
    response_model=CompanyResponse,
    summary="Get current user's company (Authenticated)",
    description="Retrieve the company owned by the current user"
)
async def get_my_company(
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Get the company owned by the current user"""
    try:
        user_uuid = UUID(current_user["sub"])
        companies = await DB.get_companies_by_user_uuid(conn=db, user_uuid=user_uuid)

        if not companies:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You don't have a company yet. Create one first."
            )

        company = companies[0]

        # Translate fields
        lang = "es"
        company["name"] = translate_field(company["name"], lang)
        company["description"] = translate_field(company["description_es"], lang)
        company["product_name"] = translate_field(company["product_name_es"], lang)

        return CompanyResponse(**company)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_my_company_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve your company")


# ============================================================================
# ADMIN-ONLY ENDPOINTS - Requires admin authentication
# ============================================================================

@router.get(
    "/admin/all-companies//use-postman-or-similar-to-send-csrf",
    response_model=List[CompanyResponse],
    summary="List all companies (Admin Only)",
    description="Retrieve a paginated list of all companies - admin authentication required"
)
async def admin_list_all_companies(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """List all companies - admin only"""
    try:
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin users can view all companies")

        companies = await DB.get_all_companies(conn=db, limit=limit, offset=offset)

        # Translate fields
        translated = []
        for company in companies:
            translated.append({
                **company,
                "name": translate_field(company["name"], "es"),
                "description": translate_field(company["description_es"], "es"),
                "product_name": translate_field(company["product_name_es"], "es")
            })

        logger.info("admin_list_all_companies", admin_email=current_user["email"], companies_count=len(translated))
        return [CompanyResponse(**c) for c in translated]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin_list_companies_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve companies")


@router.delete(
    "/admin/{company_uuid}/use-postman-or-similar-to-send-csrf",
    status_code=status.HTTP_200_OK,
    summary="Delete any company by UUID (Admin Only)",
    description="Admin can delete any company regardless of ownership"
)
async def admin_delete_company(
    company_uuid: UUID,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Delete any company - admin only."""
    try:
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin users can delete any company")

        result = await DB.admin_delete_company_by_uuid(conn=db, company_uuid=company_uuid, admin_email=current_user["email"])


        # Translate fields
        result["name"] = translate_field(result["name"], "es")

        logger.info("admin_deleted_company", company_uuid=str(company_uuid), company_name=result["name"], admin_email=current_user["email"])
        return {"message": "Company successfully deleted by admin", "uuid": result["uuid"], "name": result["name"]}

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("admin_delete_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete company")
