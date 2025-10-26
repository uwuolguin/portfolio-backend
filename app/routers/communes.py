from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from uuid import UUID
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.auth.dependencies import  verify_csrf, require_admin
from app.schemas.communes import CommuneCreate, CommuneUpdate, CommuneResponse
from app.cache.decorators import cache_response
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/communes",
    tags=["communes"]
)


@router.get("/", response_model=List[CommuneResponse])
@cache_response(key_prefix="communes:all", ttl=3600)  # Cache for 1 hour
async def list_communes(
    db: asyncpg.Connection = Depends(get_db)
):
    """Public endpoint - cached for 1 hour"""
    communes = await DB.get_all_communes(conn=db)
    return [CommuneResponse(**commune) for commune in communes]


@router.post(
    "/use-postman-or-similar-to-send-csrf",
    response_model=CommuneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new commune (Admin Only)"
)
async def create_commune(
    commune_data: CommuneCreate,
    current_user: dict = Depends(require_admin), 
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        commune = await DB.create_commune(
            conn=db,
            name=commune_data.name,
            user_email=current_user["email"]
        )
        return CommuneResponse(**commune)
        
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error("create_commune_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to create commune"
        )


@router.put(
    "/{commune_uuid}/use-postman-or-similar-to-send-csrf",
    response_model=CommuneResponse,
    summary="Update a commune (Admin Only)"
)
async def update_commune(
    commune_uuid: UUID,
    commune_data: CommuneUpdate,
    current_user: dict = Depends(require_admin), 
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    try:
        commune = await DB.update_commune_by_uuid(
            conn=db,
            commune_uuid=commune_uuid,
            name=commune_data.name,
            user_email=current_user["email"]
        )
        return CommuneResponse(**commune)
        
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("update_commune_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to update commune"
        )


@router.delete(
    "/{commune_uuid}/use-postman-or-similar-to-send-csrf",
    status_code=status.HTTP_200_OK,
    summary="Delete a commune (Admin Only)"
)
async def delete_commune(
    commune_uuid: UUID,
    current_user: dict = Depends(require_admin),  
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("commune_delete_unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to delete commune"
        )