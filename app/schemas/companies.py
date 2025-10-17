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
    description_es: Optional[str] = Field(..., max_length=500, description="Spanish description")
    description_en: Optional[str] = Field(..., max_length=500, description="English description")
    address: Optional[str] = Field(..., max_length=200, description="Physical address")
    phone: Optional[str] = Field(..., max_length=50, description="Contact phone number")
    email: Optional[EmailStr] = Field(..., description="Contact email")
    image_url: Optional[str] = Field(..., max_length=10000, description="Company image URL")

class CompanyUpdate(BaseModel):
    """Schema for updating a company (all fields optional)"""
    product_uuid: Optional[UUID] = Field(..., description="UUID of the product")
    commune_uuid: Optional[UUID] = Field(..., description="UUID of the commune")
    name: Optional[str] = Field(..., min_length=1, max_length=100, description="Company name")
    description_es: Optional[str] = Field(..., max_length=500, description="Spanish description")
    description_en: Optional[str] = Field(..., max_length=500, description="English description")
    address: Optional[str] = Field(..., max_length=200, description="Physical address")
    phone: Optional[str] = Field(..., max_length=50, description="Contact phone number")
    email: Optional[EmailStr] = Field(..., description="Contact email")
    image_url: Optional[str] = Field(..., max_length=2000, description="Company image URL")


class CompanyResponse(BaseModel):
    """Schema for company response with all data"""
    uuid: UUID
    user_uuid: UUID
    product_uuid: UUID
    commune_uuid: UUID
    name: str
    description_es: Optional[str] = None
    description_en: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    product_name_es: Optional[str] = None
    product_name_en: Optional[str] = None
    commune_name: Optional[str] = None

class CompanySearchResponse(BaseModel):
    """Schema for company search results from materialized view"""
    uuid: UUID
    name: str
    description: Optional[str] = Field(..., description="Description in requested language")
    address: Optional[str] = None
    email: Optional[str] = None
    product_name: Optional[str] = Field(..., description="Product name in requested language")
    commune_name: Optional[str] = None
    relevance_score: float = Field(..., description="Search relevance score", ge=0.0)
