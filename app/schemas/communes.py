# app/schemas/communes.py
"""
Pydantic schemas for Commune endpoints.
These define the request/response structure and validation rules.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime



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
    

class CommuneUpdate(BaseModel):
    """
    Schema for updating a commune.
    
    Used by: PUT /communes/{commune_uuid}
    Admin only endpoint.
    """
    name: str = Field(
        ...,
        min_length=1, 
        max_length=100, 
        description="New commune name"
    )
    


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
    