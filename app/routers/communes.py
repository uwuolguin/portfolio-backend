# app/routers/communes.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from uuid import UUID
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.auth.dependencies import get_current_user, verify_csrf
from app.schemas.communes import CommuneCreate, CommuneUpdate, CommuneResponse
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/communes",
    tags=["communes"]
)


# ============================================================================
# PUBLIC ENDPOINTS - No authentication required
# ============================================================================

@router.get(
    "/",
    response_model=List[CommuneResponse],
    summary="List all communes (Public)",
    description="Retrieve all communes - no authentication required"
)
async def list_communes(
    limit: int = Query(500, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: asyncpg.Connection = Depends(get_db)
):
    """List all communes - public endpoint"""
    try:
        query = """
            SELECT uuid, name, created_at
            FROM fastapi.communes
            ORDER BY name ASC
            LIMIT $1 OFFSET $2
        """
        rows = await db.fetch(query, limit, offset)
        return [CommuneResponse(**dict(row)) for row in rows]
    except Exception as e:
        logger.error("list_communes_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve communes"
        )


@router.get(
    "/{commune_uuid}",
    response_model=CommuneResponse,
    summary="Get commune by UUID (Public)",
    description="Retrieve a specific commune by UUID"
)
async def get_commune(
    commune_uuid: UUID,
    db: asyncpg.Connection = Depends(get_db)
):
    """Get a single commune by UUID - public endpoint"""
    try:
        query = """
            SELECT uuid, name, created_at
            FROM fastapi.communes
            WHERE uuid = $1
        """
        row = await db.fetchrow(query, commune_uuid)
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Commune with UUID {commune_uuid} not found"
            )
        
        return CommuneResponse(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_commune_error", commune_uuid=str(commune_uuid), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve commune"
        )


# ============================================================================
# ADMIN-ONLY ENDPOINTS - Requires admin authentication
# ============================================================================

@router.post(
    "/",
    response_model=CommuneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new commune (Admin Only)",
    description="Create a new commune - admin authentication required"
)
async def create_commune(
    commune_data: CommuneCreate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Create a new commune - admin only"""
    try:
        # Check if user is admin
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can create communes"
            )
        
        # Check if commune with same name already exists
        existing = await db.fetchval(
            "SELECT 1 FROM fastapi.communes WHERE name = $1",
            commune_data.name
        )
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Commune with this name already exists"
            )
        
        # Insert commune
        insert_query = """
            INSERT INTO fastapi.communes (name)
            VALUES ($1)
            RETURNING uuid, name, created_at
        """
        
        row = await db.fetchrow(insert_query, commune_data.name)
        
        logger.info(
            "commune_created",
            commune_uuid=str(row["uuid"]),
            admin_email=current_user["email"]
        )
        
        return CommuneResponse(**dict(row))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_commune_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create commune"
        )


@router.put(
    "/{commune_uuid}",
    response_model=CommuneResponse,
    summary="Update a commune (Admin Only)",
    description="Update a commune - admin authentication required"
)
async def update_commune(
    commune_uuid: UUID,
    commune_data: CommuneUpdate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """Update a commune - admin only"""
    try:
        # Check if user is admin
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can update communes"
            )
        
        # Check if commune exists
        existing = await db.fetchval(
            "SELECT 1 FROM fastapi.communes WHERE uuid = $1",
            commune_uuid
        )
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Commune with UUID {commune_uuid} not found"
            )
        
        if commune_data.name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name is required for update"
            )
        
        # Update commune
        update_query = """
            UPDATE fastapi.communes
            SET name = $1
            WHERE uuid = $2
            RETURNING uuid, name, created_at
        """
        
        row = await db.fetchrow(update_query, commune_data.name, commune_uuid)
        
        # Refresh materialized view since commune names are indexed
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "commune_updated",
            commune_uuid=str(commune_uuid),
            admin_email=current_user["email"]
        )
        
        return CommuneResponse(**dict(row))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_commune_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update commune"
        )


@router.delete(
    "/{commune_uuid}",
    status_code=status.HTTP_200_OK,
    summary="Delete a commune (Admin Only)",
    description="Delete a commune - admin authentication required, fails if companies use it"
)
async def delete_commune(
    commune_uuid: UUID,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """
    Delete a commune - admin only.
    
    This endpoint will fail if any companies are currently located in this commune.
    The commune must be unused before it can be deleted.
    
    Process:
    1. Verify user is admin
    2. Check if commune exists
    3. Check if any companies reference this commune
    4. If no companies use it, move to communes_deleted table
    5. Delete from communes table
    6. Refresh materialized view
    
    Returns:
        Success message with commune UUID and name
    
    Raises:
        403: User is not admin
        404: Commune not found
        400: Commune is still being used by companies
        500: Database error
    """
    try:
        # Step 1: Check if user is admin
        if not DB.is_admin(current_user["email"]):
            logger.warning(
                "commune_delete_unauthorized",
                commune_uuid=str(commune_uuid),
                user_email=current_user["email"]
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can delete communes"
            )
        
        # Step 2-5: Call the database transaction
        # This function in DB class handles:
        # - Checking commune exists
        # - Checking if companies are located in this commune
        # - Moving to communes_deleted table
        # - Actual deletion from communes table
        result = await DB.delete_commune_by_uuid(
            conn=db,
            commune_uuid=commune_uuid,
            user_email=current_user["email"]
        )
        
        # Step 6: Refresh materialized view
        # This ensures search results are updated immediately
        # Since commune names are part of the search vector
        await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "commune_deleted_successfully",
            commune_uuid=str(commune_uuid),
            commune_name=result["name"],
            admin_email=current_user["email"]
        )
        
        return {
            "message": "Commune successfully deleted",
            "uuid": result["uuid"],
            "name": result["name"]
        }
        
    except PermissionError as e:
        # Raised when user doesn't have admin permissions
        # This shouldn't happen since we check admin status above,
        # but the DB function also checks, so we handle it here for safety
        logger.error(
            "commune_delete_permission_error",
            commune_uuid=str(commune_uuid),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        # Raised when:
        # - Commune doesn't exist in the database
        # - Commune is being used by one or more companies
        # The error message from DB will specify which case it is
        logger.warning(
            "commune_delete_validation_error",
            commune_uuid=str(commune_uuid),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Catch-all for unexpected database errors
        # Examples: connection timeout, database constraint violations, etc.
        logger.error(
            "commune_delete_unexpected_error",
            commune_uuid=str(commune_uuid),
            error=str(e),
            exc_info=True  # This logs the full stack trace for debugging
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete commune"
        )