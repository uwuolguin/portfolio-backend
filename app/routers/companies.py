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


@router.get(
    "/search",
    response_model=List[CompanySearchResponse],
    summary="Search companies (Public)"
)
async def search_companies(
    q: str = Query(..., min_length=1),
    lang: str = Query("es", regex="^(es|en)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: asyncpg.Connection = Depends(get_db)
):
    try:
        results = await DB.search_companies(conn=db, query=q, lang=lang, limit=limit, offset=offset)
        return [CompanySearchResponse(**res) for res in results]
    except Exception as e:
        logger.error("company_search_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to search companies")


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    company_data: CompanyCreate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        user_uuid = UUID(current_user["sub"])
        if company_data.lang == "es":
            description_es, description_en = await translate_field(
                field_name="company_description",
                text_es=company_data.description_es,
                text_en=None
            )
        else:
            description_es, description_en = await translate_field(
                field_name="company_description",
                text_es=None,
                text_en=company_data.description_en
            )
        
        logger.info(
            "creating_company_with_translation",
            lang=company_data.lang,
            original_desc_es=company_data.description_es,
            original_desc_en=company_data.description_en,
            final_desc_es=description_es,
            final_desc_en=description_en
        )
        
        company = await DB.create_company(
            conn=db,
            user_uuid=user_uuid,
            product_uuid=company_data.product_uuid,
            commune_uuid=company_data.commune_uuid,
            name=company_data.name,
            description_es=description_es,
            description_en=description_en,
            address=company_data.address,
            phone=company_data.phone,
            email=company_data.email,
            image_url=company_data.image_url
        )
        
        logger.info("company_created", company_uuid=str(company["uuid"]), user_uuid=str(user_uuid))
        return CompanyResponse(**company)
        
    except ValueError as e:
        if "already have a company" in str(e) or "can only create one company" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("create_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create company")
    
@router.put("/{company_uuid}", response_model=CompanyResponse)
async def update_company(
    company_uuid: UUID,
    company_data: CompanyUpdate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        user_uuid = UUID(current_user["sub"])
        description_es = company_data.description_es
        description_en = company_data.description_en
        
        if company_data.lang:
            if company_data.lang == "es":
                description_es, description_en = await translate_field(
                    field_name="company_description",
                    text_es=company_data.description_es,
                    text_en=None
                )
            else:
                description_es, description_en = await translate_field(
                    field_name="company_description",
                    text_es=None,
                    text_en=company_data.description_en
                )
            
            logger.info(
                "updating_company_with_translation",
                company_uuid=str(company_uuid),
                lang=company_data.lang,
                original_desc_es=company_data.description_es,
                original_desc_en=company_data.description_en,
                final_desc_es=description_es,
                final_desc_en=description_en
            )
        
        company = await DB.update_company_by_uuid(
            conn=db,
            company_uuid=company_uuid,
            user_uuid=user_uuid,
            name=company_data.name,
            description_es=description_es,
            description_en=description_en,
            address=company_data.address,
            phone=company_data.phone,
            email=company_data.email,
            image_url=company_data.image_url,
            product_uuid=company_data.product_uuid,
            commune_uuid=company_data.commune_uuid
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


@router.delete("/{company_uuid}", status_code=status.HTTP_200_OK)
async def delete_company(
    company_uuid: UUID,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        user_uuid = UUID(current_user["sub"])
        result = await DB.delete_company_by_uuid(conn=db, company_uuid=company_uuid, user_uuid=user_uuid)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found or no permission")
        return {"message": "Company successfully deleted", "uuid": str(company_uuid)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete company")


@router.get("/user/my-company", response_model=CompanyResponse)
async def get_my_company(
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    try:
        user_uuid = UUID(current_user["sub"])
        companies = await DB.get_companies_by_user_uuid(conn=db, user_uuid=user_uuid)
        if not companies:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You don't have a company yet")
        company = companies[0]
        return CompanyResponse(**company)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_my_company_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve your company")


@router.get("/admin/all-companies//use-postman-or-similar-to-send-csrf", response_model=List[CompanyResponse])
async def admin_list_all_companies(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    try:
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin users can view all companies")
        companies = await DB.get_all_companies(conn=db, limit=limit, offset=offset)
        return [CompanyResponse(**c) for c in companies]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin_list_companies_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve companies")


@router.delete("/admin/{company_uuid}/use-postman-or-similar-to-send-csrf", status_code=status.HTTP_200_OK)
async def admin_delete_company(
    company_uuid: UUID,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin users can delete any company")
        result = await DB.admin_delete_company_by_uuid(conn=db, company_uuid=company_uuid, admin_email=current_user["email"])
        return {"message": "Company successfully deleted by admin", "uuid": result["uuid"], "name": result["name"]}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("admin_delete_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete company")
