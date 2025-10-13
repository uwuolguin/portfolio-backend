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
        query = """
            SELECT uuid, name_es, name_en, created_at
            FROM fastapi.products
            ORDER BY name_en ASC
            LIMIT $1 OFFSET $2
        """
        rows = await db.fetch(query, limit, offset)
        return [ProductResponse(**dict(row)) for row in rows]
    except Exception as e:
        logger.error("list_products_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve products"
        )


@router.get(
    "/{product_uuid}",
    response_model=ProductResponse,
    summary="Get product by UUID (Public)",
    description="Retrieve a specific product by UUID"
)
async def get_product(
    product_uuid: UUID,
    db: asyncpg.Connection = Depends(get_db)
):
    """Get a single product by UUID - public endpoint"""
    try:
        query = """
            SELECT uuid, name_es, name_en, created_at
            FROM fastapi.products
            WHERE uuid = $1
        """
        row = await db.fetchrow(query, product_uuid)
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with UUID {product_uuid} not found"
            )
        
        return ProductResponse(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_product_error", product_uuid=str(product_uuid), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product"
        )


@router.post(
    "/",
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
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can create products"
            )
        
        existing = await db.fetchval(
            "SELECT 1 FROM fastapi.products WHERE name_en = $1 OR name_es = $2",
            product_data.name_en,
            product_data.name_es
        )
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product with this name already exists"
            )
        
        insert_query = """
            INSERT INTO fastapi.products (name_es, name_en)
            VALUES ($1, $2)
            RETURNING uuid, name_es, name_en, created_at
        """
        
        row = await db.fetchrow(
            insert_query,
            product_data.name_es,
            product_data.name_en
        )
        
        logger.info(
            "product_created",
            product_uuid=str(row["uuid"]),
            admin_email=current_user["email"]
        )
        
        return ProductResponse(**dict(row))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product"
        )


@router.put(
    "/{product_uuid}",
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
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can update products"
            )
        
        existing = await db.fetchval(
            "SELECT 1 FROM fastapi.products WHERE uuid = $1",
            product_uuid
        )
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with UUID {product_uuid} not found"
            )
        
        update_fields = []
        params = []
        param_count = 1
        
        if product_data.name_es is not None:
            update_fields.append(f"name_es = ${param_count}")
            params.append(product_data.name_es)
            param_count += 1
        
        if product_data.name_en is not None:
            update_fields.append(f"name_en = ${param_count}")
            params.append(product_data.name_en)
            param_count += 1
        
        if not update_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update"
            )
        
        params.append(product_uuid)
        
        update_query = f"""
            UPDATE fastapi.products
            SET {', '.join(update_fields)}
            WHERE uuid = ${param_count}
            RETURNING uuid, name_es, name_en, created_at
        """
        
        row = await db.fetchrow(update_query, *params)
        
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "product_updated",
            product_uuid=str(product_uuid),
            admin_email=current_user["email"]
        )
        
        return ProductResponse(**dict(row))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_product_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product"
        )


@router.delete(
    "/{product_uuid}",
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
    """Delete a product - admin only, fails if any companies are using it"""
    try:
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can delete products"
            )
        
        result = await DB.delete_product_by_uuid(
            conn=db,
            product_uuid=product_uuid,
            user_email=current_user["email"]
        )
        
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
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
