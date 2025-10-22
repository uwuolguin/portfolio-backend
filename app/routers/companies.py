from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request,Query,Form
from typing import List, Optional
from uuid import UUID
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.auth.dependencies import get_current_user, verify_csrf
from app.schemas.companies import CompanyResponse, CompanySearchResponse
from app.auth.dependencies import get_current_user, verify_csrf, require_admin, require_verified_email
from app.utils.translator import translate_field
from app.utils.file_handler import FileHandler
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/companies", tags=["companies"])
@router.get(
    "/search",
    response_model=List[CompanySearchResponse],
    summary="Search companies (Public)"
)
async def search_companies(
    q: Optional[str] = Query(None, min_length=1, description="Search query, optional"),
    lang: str = Query("es", pattern="^(es|en)$"),
    commune: Optional[str] = Query(None, description="Filter by commune name"),
    product: Optional[str] = Query(None, description="Filter by product name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: asyncpg.Connection = Depends(get_db)
):
    try:
        results = await DB.search_companies(
            conn=db,
            query=q or "",
            lang=lang,
            commune=commune,
            product=product,
            limit=limit,
            offset=offset
        )
        return [CompanySearchResponse(**res) for res in results]
    except Exception as e:
        logger.error("company_search_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to search companies")


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    request: Request,
    name: str = Form(..., min_length=1, max_length=100),
    product_uuid: UUID = Form(...),
    commune_uuid: UUID = Form(...),
    description_es: Optional[str] = Form(None, max_length=100),
    description_en: Optional[str] = Form(None, max_length=100),
    address: str = Form(..., min_length=5, max_length=100),
    phone: str = Form(..., max_length=100),
    email: str = Form(..., max_length=100),
    lang: str = Form(..., pattern="^(es|en)$"),
    image: UploadFile = File(...),
    current_user: dict = Depends(require_verified_email),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        user_uuid = UUID(current_user["sub"])
        
        # Validate descriptions
        if not description_es and not description_en:
            raise HTTPException(
                status_code=400,
                detail="At least one description must be provided"
            )
        
        # Translate description
        if lang == "es":
            description_es, description_en = await translate_field(
                "company_description",
                description_es,
                None
            )
        else:
            description_es, description_en = await translate_field(
                "company_description",
                None,
                description_en
            )
        
        # Get base URL for NSFW check
        base_url = str(request.base_url).rstrip('/')
        
        # Save and process image with NSFW check
        # This is async and non-blocking!
        image_path = await FileHandler.save_image(
            file=image,
            check_nsfw=settings.enable_content_moderation,  # Enable NSFW check
            public_base_url=base_url
        )
        
        try:
            # Create company in database
            company = await DB.create_company(
                conn=db,
                user_uuid=user_uuid,
                product_uuid=product_uuid,
                commune_uuid=commune_uuid,
                name=name,
                description_es=description_es,
                description_en=description_en,
                address=address,
                phone=phone,
                email=email,
                image_url=image_path
            )
            
            # Prepare response with public URL
            response_data = dict(company)
            response_data["image_url"] = FileHandler.get_image_url(
                image_path,
                base_url
            )
            
            logger.info(
                "company_created_with_verified_image",
                company_uuid=str(company["uuid"]),
                user_uuid=str(user_uuid)
            )
            
            return CompanyResponse(**response_data)
            
        except Exception as db_error:
            # Rollback: delete saved image on DB error
            FileHandler.delete_image(image_path)
            raise db_error
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_company_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to create company"
        )

@router.put("/{company_uuid}", response_model=CompanyResponse)
async def update_company(
    company_uuid: UUID,
    request: Request,
    name: Optional[str] = Form(None, min_length=1, max_length=100),
    product_uuid: Optional[UUID] = Form(None),
    commune_uuid: Optional[UUID] = Form(None),
    description_es: Optional[str] = Form(None, max_length=100),
    description_en: Optional[str] = Form(None, max_length=100),
    address: Optional[str] = Form(None, min_length=5, max_length=100),
    phone: Optional[str] = Form(None, max_length=100),
    email: Optional[str] = Form(None, max_length=100),
    lang: Optional[str] = Form(None, pattern="^(es|en)$"),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(require_verified_email),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        user_uuid = UUID(current_user["sub"])
        
        # Translate descriptions if provided
        final_description_es = description_es
        final_description_en = description_en
        
        if (description_es or description_en) and lang:
            if lang == "es":
                final_description_es, final_description_en = await translate_field(
                    "company_description",
                    description_es,
                    None
                )
            else:
                final_description_es, final_description_en = await translate_field(
                    "company_description",
                    None,
                    description_en
                )
        
        # Handle image update with NSFW check
        new_image_path = None
        old_image_path = None
        
        if image:
            # Get old image path for cleanup
            old_company = await DB.get_company_by_uuid(conn=db, company_uuid=company_uuid)
            if old_company:
                old_image_path = old_company.get("image_url")
            
            # Get base URL for NSFW check
            base_url = str(request.base_url).rstrip('/')
            
            # Save and process new image with NSFW check (async, non-blocking)
            new_image_path = await FileHandler.save_image(
                file=image,
                company_uuid=str(company_uuid),
                check_nsfw=settings.enable_content_moderation,  # Enable NSFW check
                public_base_url=base_url
            )
        
        # Update company in database
        company = await DB.update_company_by_uuid(
            conn=db,
            company_uuid=company_uuid,
            user_uuid=user_uuid,
            name=name,
            description_es=final_description_es,
            description_en=final_description_en,
            address=address,
            phone=phone,
            email=email,
            image_url=new_image_path,
            product_uuid=product_uuid,
            commune_uuid=commune_uuid
        )
        
        # Clean up old image after successful update
        if new_image_path and old_image_path and old_image_path != new_image_path:
            FileHandler.delete_image(old_image_path)
        
        # Prepare response
        response_data = dict(company)
        response_data["image_url"] = FileHandler.get_image_url(
            company["image_url"],
            str(request.base_url).rstrip('/')
        )
        
        logger.info(
            "company_updated_with_verified_image",
            company_uuid=str(company_uuid),
            user_uuid=str(user_uuid),
            new_image=bool(new_image_path)
        )
        
        return CompanyResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_company_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to update company"
        )


@router.delete("/{company_uuid}", status_code=status.HTTP_200_OK)
async def delete_company(
    company_uuid: UUID,
    current_user: dict = Depends(require_verified_email),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        user_uuid = UUID(current_user["sub"])
        
        company = await DB.get_company_by_uuid(conn=db, company_uuid=company_uuid)
        if company and company.get("user_uuid") == user_uuid:
            image_path = company.get("image_url")
            
            result = await DB.delete_company_by_uuid(conn=db, company_uuid=company_uuid, user_uuid=user_uuid)
            
            if result:
                if image_path:
                    FileHandler.delete_image(image_path)
                
                return {"message": "Company successfully deleted", "uuid": str(company_uuid)}
        
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found or no permission")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete company")


@router.get("/user/my-company", response_model=CompanyResponse)
async def get_my_company(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    try:
        user_uuid = UUID(current_user["sub"])
        companies = await DB.get_companies_by_user_uuid(conn=db, user_uuid=user_uuid)
        if not companies:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You don't have a company yet")
        
        company = companies[0]
        
        response_data = dict(company)
        response_data["image_url"] = FileHandler.get_image_url(
            company["image_url"],
            str(request.base_url).rstrip('/')
        )
        
        return CompanyResponse(**response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_my_company_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve your company")


@router.get("/admin/all-companies/use-postman-or-similar-to-send-csrf", response_model=List[CompanyResponse])
async def admin_list_all_companies(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_admin), 
    db: asyncpg.Connection = Depends(get_db)
):
    try:
        companies = await DB.get_all_companies(conn=db, limit=limit, offset=offset)
        
        base_url = str(request.base_url).rstrip('/')
        response_companies = []
        for company in companies:
            company_data = dict(company)
            company_data["image_url"] = FileHandler.get_image_url(company["image_url"], base_url)
            response_companies.append(CompanyResponse(**company_data))
        
        return response_companies
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin_list_companies_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to retrieve companies"
        )

@router.delete("/admin/{company_uuid}/use-postman-or-similar-to-send-csrf", status_code=status.HTTP_200_OK)
async def admin_delete_company(
    company_uuid: UUID,
    current_user: dict = Depends(require_admin), 
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        result = await DB.admin_delete_company_by_uuid(
            conn=db,
            company_uuid=company_uuid,
            admin_email=current_user["email"]
        )

        from app.utils.file_handler import FileHandler
        image_path = result.get("image_url")
        if image_path:
            FileHandler.delete_image(image_path)

        return {
            "message": "Company successfully deleted by admin",
            "uuid": result["uuid"],
            "name": result["name"]
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error("admin_delete_company_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete company")
