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
        communes = await DB.get_all_communes(conn=db, limit=limit, offset=offset)
        return [CommuneResponse(**commune) for commune in communes]
    except Exception as e:
        logger.error("list_communes_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve communes"
        )


# ============================================================================
# ADMIN-ONLY ENDPOINTS - Requires admin authentication
# ============================================================================

@router.post(
    "/use-postman-or-similar-to-send-csrf",
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
        commune = await DB.create_commune(
            conn=db,
            name=commune_data.name,
            user_email=current_user["email"]
        )
        return CommuneResponse(**commune)
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
        logger.error("create_commune_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create commune"
        )


@router.put(
    "/{commune_uuid}/use-postman-or-similar-to-send-csrf",
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
        commune = await DB.update_commune_by_uuid(
            conn=db,
            commune_uuid=commune_uuid,
            name=commune_data.name,
            user_email=current_user["email"]
        )

        return CommuneResponse(**commune)
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
        logger.error("update_commune_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update commune"
        )


@router.delete(
    "/{commune_uuid}/use-postman-or-similar-to-send-csrf",
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
    """Delete a commune - admin only"""
    try:
        result = await DB.delete_commune_by_uuid(
            conn=db,
            commune_uuid=commune_uuid,
            user_email=current_user["email"]
        )
        
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
        logger.error("commune_delete_unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete commune"
        )