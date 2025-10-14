# app/schemas/communes.py
"""
Pydantic schemas for Commune endpoints.
These define the request/response structure and validation rules.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class CommuneCreate(BaseModel):
    """
    Schema for creating a new commune.
    
    Used by: POST /communes/
    Admin only endpoint.
    """
    name: str = Field(
        ..., 
        min_length=1, 
        max_length=100, 
        description="Commune name (e.g., 'Santiago', 'Valparaíso')"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Viña del Mar"
            }
        }


class CommuneUpdate(BaseModel):
    """
    Schema for updating a commune.
    
    Used by: PUT /communes/{commune_uuid}
    Admin only endpoint.
    
    Note: Currently only name can be updated.
    If you want to make it optional later, change to: Optional[str] = None
    """
    name: Optional[str] = Field(
        None,
        min_length=1, 
        max_length=100, 
        description="New commune name"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Santiago Centro"
            }
        }


class CommuneResponse(BaseModel):
    """
    Schema for commune response.
    
    Used by:
    - GET /communes/ (list)
    - GET /communes/{commune_uuid} (single)
    - POST /communes/ (after creation)
    - PUT /communes/{commune_uuid} (after update)
    
    Returns all commune data including metadata.
    """
    uuid: UUID = Field(..., description="Unique identifier for the commune")
    name: str = Field(..., description="Commune name")
    created_at: datetime = Field(..., description="Timestamp when commune was created")
    
    class Config:
        json_schema_extra = {
            "example": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Santiago",
                "created_at": "2025-09-28T17:33:58.664718"
            }
        }