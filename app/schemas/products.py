# app/schemas/products.py
from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


class ProductCreate(BaseModel):
    """
    Schema for creating a new product.
    Provide at least ONE name (Spanish or English).
    The missing one will be auto-translated.
    """
    name_es: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=100, 
        description="Spanish product name (optional if name_en provided)"
    )
    name_en: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=100, 
        description="English product name (optional if name_es provided)"
    )
    
    @model_validator(mode='after')
    def check_at_least_one_name(self):
        """Ensure at least one name is provided"""
        if not self.name_es and not self.name_en:
            raise ValueError("At least one product name (name_es or name_en) must be provided")
        return self


class ProductUpdate(BaseModel):
    """
    Schema for updating a product.
    All fields optional. If only one name provided, will auto-translate.
    """
    name_es: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=100, 
        description="Spanish product name"
    )
    name_en: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=100, 
        description="English product name"
    )

    @model_validator(mode='after')
    def check_at_least_one_name(self):
        """Ensure at least one name is provided, thre is no reason to hit the endpoint if not"""
        if not self.name_es and not self.name_en:
            raise ValueError("At least one product name (name_es or name_en) must be provided")
        return self

class ProductResponse(BaseModel):
    """Schema for product response"""
    uuid: UUID
    name_es: str
    name_en: str
    created_at: datetime