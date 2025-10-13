# app/schemas/communes.py
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class CommuneCreate(BaseModel):
    """Schema for creating a new commune"""
    name: str = Field(..., min_length=1, max_length=100, description="Commune name")


class CommuneUpdate(BaseModel):
    """Schema for updating a commune"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Commune name")


class CommuneResponse(BaseModel):
    """Schema for commune response"""
    uuid: UUID
    name: str
    created_at: datetime
