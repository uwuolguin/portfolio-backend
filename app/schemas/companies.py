# app/schemas/companies.py
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from uuid import UUID
from datetime import datetime
from typing import Optional


class CompanyCreate(BaseModel):
    """Schema for creating a new company"""
    product_uuid: UUID = Field(..., description="UUID of the product")
    commune_uuid: UUID = Field(..., description="UUID of the commune")
    name: str = Field(..., min_length=1, max_length=100, description="Company name")
    description_es: Optional[str] = Field(None, max_length=100, description="Spanish description")
    description_en: Optional[str] = Field(None, max_length=100, description="English description")
    address: Optional[str] = Field(None, max_length=100, description="Physical address")
    phone: Optional[str] = Field(None, max_length=100, description="Contact phone number")
    email: Optional[EmailStr] = Field(None, description="Contact email")
    image_url: Optional[str] = Field(None, max_length=10000, description="Company image URL")


class CompanyUpdate(BaseModel):
    """Schema for updating a company (all fields optional)"""
    product_uuid: Optional[UUID] = Field(None, description="UUID of the product")
    commune_uuid: Optional[UUID] = Field(None, description="UUID of the commune")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Company name")
    description_es: Optional[str] = Field(None, max_length=100, description="Spanish description")
    description_en: Optional[str] = Field(None, max_length=100, description="English description")
    address: Optional[str] = Field(None, max_length=100, description="Physical address")
    phone: Optional[str] = Field(None, max_length=100, description="Contact phone number")
    email: Optional[EmailStr] = Field(None, description="Contact email")
    image_url: Optional[str] = Field(None, max_length=10000, description="Company image URL")


class CompanyResponse(BaseModel):
    """Schema for company response with all data"""
    uuid: UUID
    user_uuid: UUID
    product_uuid: UUID
    commune_uuid: UUID
    name: str
    description_es: Optional[str]
    description_en: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    image_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    # Joined data
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    product_name_es: Optional[str] = None
    product_name_en: Optional[str] = None
    commune_name: Optional[str] = None


class CompanySearchResponse(BaseModel):
    """Schema for company search results from materialized view"""
    uuid: UUID
    name: str
    description: Optional[str] = Field(None, description="Description in requested language")
    address: Optional[str]
    email: Optional[str]
    product_name: Optional[str] = Field(None, description="Product name in requested language")
    commune_name: Optional[str]
    relevance_score: float = Field(..., description="Search relevance score")


# ============================================================================
