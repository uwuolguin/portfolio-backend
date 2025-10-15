# app/routers/products.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from uuid import UUID
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.auth.dependencies import get_current_user, verify_csrf
from app.schemas.products import ProductCreate, ProductUpdate, ProductResponse
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/products",
    tags=["products"]
)


# ============================================================================
# PUBLIC ENDPOINTS - No authentication required
# ============================================================================

@router.get(
    "/",
    response_model=List[ProductResponse],
    summary="List all products (Public)",
    description="Retrieve all products - no authentication required"
)
async def list_products(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: asyncpg.Connection = Depends(get_db)
):
    """List all products - public endpoint"""
    try:
        products = await DB.get_all_products(conn=db, limit=limit, offset=offset)
        return [ProductResponse(**product) for product in products]
    except Exception as e:
        logger.error("list_products_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve products"
        )




# ============================================================================
# ADMIN-ONLY ENDPOINTS - Requires admin authentication
# ============================================================================

@router.post(
    "/use-postman-or-similar-to-send-csrf",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product (Admin Only)",
    description="Create a new product - admin authentication required"
)
async def create_product(
    product_data: ProductCreate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Create a new product - admin only"""
    try:
        product = await DB.create_product(
            conn=db,
            name_es=product_data.name_es,
            name_en=product_data.name_en,
            user_email=current_user["email"]
        )
        logger.info(
            "product_created",
            product_uuid=str(product["uuid"]),
            admin_email=current_user["email"]
        )
        return ProductResponse(**product)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error("create_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product"
        )


@router.put(
    "/{product_uuid}/use-postman-or-similar-to-send-csrf",
    response_model=ProductResponse,
    summary="Update a product (Admin Only)",
    description="Update a product - admin authentication required"
)
async def update_product(
    product_uuid: UUID,
    product_data: ProductUpdate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Update a product - admin only"""
    try:
        product = await DB.update_product_by_uuid(
            conn=db,
            product_uuid=product_uuid,
            name_es=product_data.name_es,
            name_en=product_data.name_en,
            user_email=current_user["email"]
        )
        
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "product_updated",
            product_uuid=str(product_uuid),
            admin_email=current_user["email"]
        )
        return ProductResponse(**product)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("update_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product"
        )


@router.delete(
    "/{product_uuid}/use-postman-or-similar-to-send-csrf",
    status_code=status.HTTP_200_OK,
    summary="Delete a product (Admin Only)",
    description="Delete a product - admin authentication required, fails if companies use it"
)
async def delete_product(
    product_uuid: UUID,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """
    Delete a product - admin only.
    
    This endpoint will fail if any companies are currently using this product.
    The product must be unused before it can be deleted.
    """
    try:
        result = await DB.delete_product_by_uuid(
            conn=db,
            product_uuid=product_uuid,
            user_email=current_user["email"]
        )
        
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "product_deleted_successfully",
            product_uuid=str(product_uuid),
            product_name=result["name_en"],
            admin_email=current_user["email"]
        )
        
        return {
            "message": "Product successfully deleted",
            "uuid": result["uuid"],
            "name": result["name_en"]
        }
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("delete_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete product"
        )