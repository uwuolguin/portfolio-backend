from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from uuid import UUID
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.utils.translator import translate_field
from app.auth.dependencies import verify_csrf, require_admin 
from app.schemas.products import ProductCreate, ProductUpdate, ProductResponse
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=List[ProductResponse])
async def list_products(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: asyncpg.Connection = Depends(get_db)
):
    """Public endpoint - no auth required"""
    try:
        products = await DB.get_all_products(conn=db, limit=limit, offset=offset)
        return [ProductResponse(**product) for product in products]
    except Exception as e:
        logger.error("list_products_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to retrieve products"
        )


@router.post("/use-postman-or-similar-to-send-csrf", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: dict = Depends(require_admin), 
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        name_es, name_en = await translate_field(
            field_name="product",
            text_es=product_data.name_es, 
            text_en=product_data.name_en
        )
        
        logger.info("creating_product_with_translation", 
                   original_name_es=product_data.name_es, 
                   original_name_en=product_data.name_en, 
                   final_name_es=name_es, 
                   final_name_en=name_en)
        
        product = await DB.create_product(
            conn=db, 
            name_es=name_es, 
            name_en=name_en, 
            user_email=current_user["email"]
        )
        
        logger.info("product_created", 
                   product_uuid=str(product["uuid"]), 
                   admin_email=current_user["email"])
        
        return ProductResponse(**product)
        
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error("create_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to create product"
        )


@router.put("/{product_uuid}/use-postman-or-similar-to-send-csrf", response_model=ProductResponse)
async def update_product(
    product_uuid: UUID,
    product_data: ProductUpdate,
    current_user: dict = Depends(require_admin),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        name_es = product_data.name_es
        name_en = product_data.name_en
        
        if name_es or name_en:
            name_es, name_en = await translate_field(
                field_name="product",
                text_es=product_data.name_es, 
                text_en=product_data.name_en
            )
            logger.info("updating_product_with_translation", 
                       product_uuid=str(product_uuid), 
                       original_name_es=product_data.name_es, 
                       original_name_en=product_data.name_en, 
                       final_name_es=name_es, 
                       final_name_en=name_en)
        
        product = await DB.update_product_by_uuid(
            conn=db, 
            product_uuid=product_uuid, 
            name_es=name_es, 
            name_en=name_en, 
            user_email=current_user["email"]
        )
        
        logger.info("product_updated", 
                   product_uuid=str(product_uuid), 
                   admin_email=current_user["email"])
        
        return ProductResponse(**product)
        
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("update_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to update product"
        )


@router.delete("/{product_uuid}/use-postman-or-similar-to-send-csrf", status_code=status.HTTP_200_OK)
async def delete_product(
    product_uuid: UUID,
    current_user: dict = Depends(require_admin),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        result = await DB.delete_product_by_uuid(
            conn=db, 
            product_uuid=product_uuid, 
            user_email=current_user["email"]
        )
        
        logger.info("product_deleted_successfully", 
                   product_uuid=str(product_uuid), 
                   product_name=result["name_en"], 
                   admin_email=current_user["email"])
        
        return {
            "message": "Product successfully deleted",
            "uuid": result["uuid"],
            "name": result["name_en"]
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("delete_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to delete product"
        )