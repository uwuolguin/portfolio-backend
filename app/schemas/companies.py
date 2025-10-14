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
    description_es: Optional[str] = Field(None, max_length=500, description="Spanish description")
    description_en: Optional[str] = Field(None, max_length=500, description="English description")
    address: Optional[str] = Field(None, max_length=200, description="Physical address")
    phone: Optional[str] = Field(None, max_length=50, description="Contact phone number")
    email: Optional[EmailStr] = Field(None, description="Contact email")
    image_url: Optional[str] = Field(None, max_length=2000, description="Company image URL")

    class Config:
        json_schema_extra = {
            "example": {
                "product_uuid": "123e4567-e89b-12d3-a456-426614174000",
                "commune_uuid": "123e4567-e89b-12d3-a456-426614174001",
                "name": "Tech Solutions SpA",
                "description_es": "Soluciones tecnológicas innovadoras",
                "description_en": "Innovative technology solutions",
                "address": "Av. Providencia 123, Santiago",
                "phone": "+56912345678",
                "email": "contact@techsolutions.cl",
                "image_url": "https://example.com/logo.png"
            }
        }


class CompanyUpdate(BaseModel):
    """Schema for updating a company (all fields optional)"""
    product_uuid: Optional[UUID] = Field(None, description="UUID of the product")
    commune_uuid: Optional[UUID] = Field(None, description="UUID of the commune")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Company name")
    description_es: Optional[str] = Field(None, max_length=500, description="Spanish description")
    description_en: Optional[str] = Field(None, max_length=500, description="English description")
    address: Optional[str] = Field(None, max_length=200, description="Physical address")
    phone: Optional[str] = Field(None, max_length=50, description="Contact phone number")
    email: Optional[EmailStr] = Field(None, description="Contact email")
    image_url: Optional[str] = Field(None, max_length=2000, description="Company image URL")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Tech Solutions SpA - Updated",
                "phone": "+56987654321",
                "address": "Av. Apoquindo 456, Las Condes"
            }
        }


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
    # Joined data
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    product_name_es: Optional[str] = None
    product_name_en: Optional[str] = None
    commune_name: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "uuid": "123e4567-e89b-12d3-a456-426614174000",
                "user_uuid": "123e4567-e89b-12d3-a456-426614174001",
                "product_uuid": "123e4567-e89b-12d3-a456-426614174002",
                "commune_uuid": "123e4567-e89b-12d3-a456-426614174003",
                "name": "Tech Solutions SpA",
                "description_es": "Soluciones tecnológicas innovadoras",
                "description_en": "Innovative technology solutions",
                "address": "Av. Providencia 123, Santiago",
                "phone": "+56912345678",
                "email": "contact@techsolutions.cl",
                "image_url": "https://example.com/logo.png",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "user_name": "John Doe",
                "user_email": "john@example.com",
                "product_name_es": "Software",
                "product_name_en": "Software",
                "commune_name": "Santiago"
            }
        }


class CompanySearchResponse(BaseModel):
    """Schema for company search results from materialized view"""
    uuid: UUID
    name: str
    description: Optional[str] = Field(None, description="Description in requested language")
    address: Optional[str] = None
    email: Optional[str] = None
    product_name: Optional[str] = Field(None, description="Product name in requested language")
    commune_name: Optional[str] = None
    relevance_score: float = Field(..., description="Search relevance score", ge=0.0)

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "uuid": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Tech Solutions SpA",
                "description": "Innovative technology solutions",
                "address": "Av. Providencia 123, Santiago",
                "email": "contact@techsolutions.cl",
                "product_name": "Software",
                "commune_name": "Santiago",
                "relevance_score": 0.8567
            }
        }