# app/schemas/products.py
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class ProductCreate(BaseModel):
    """Schema for creating a new product"""
    name_es: str = Field(..., min_length=1, max_length=100, description="Spanish product name")
    name_en: str = Field(..., min_length=1, max_length=100, description="English product name")


class ProductUpdate(BaseModel):
    """Schema for updating a product (all fields optional)"""
    name_es: Optional[str] = Field(None, min_length=1, max_length=100, description="Spanish product name")
    name_en: Optional[str] = Field(None, min_length=1, max_length=100, description="English product name")


class ProductResponse(BaseModel):
    """Schema for product response"""
    uuid: UUID
    name_es: str
    name_en: str
    created_at: datetime


# ============================================================================
