# app/schemas/companies.py
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime


class CompanyCreate(BaseModel):
    """Schema for creating a new company - ALL FIELDS REQUIRED"""
    user_uuid: UUID = Field(..., description="UUID of the user who owns the company (required)")
    product_uuid: UUID = Field(..., description="UUID of the product (required)")
    commune_uuid: UUID = Field(..., description="UUID of the commune (required)")
    name: str = Field(..., min_length=1, max_length=100, description="Company name (required)")
    description_es: str = Field(..., min_length=1, max_length=100, description="Spanish description (required)")
    description_en: str = Field(..., min_length=1, max_length=100, description="English description (required)")
    address: str = Field(..., min_length=1, max_length=100, description="Physical address (required)")
    phone: str = Field(..., min_length=1, max_length=100, description="Contact phone number (required)")
    email: EmailStr = Field(..., description="Contact email (required)")
    image_url: str = Field(..., min_length=1, max_length=10000, description="Company image URL (required)")


class CompanyUpdate(BaseModel):
    """Schema for updating a company - all fields optional for partial updates"""
    product_uuid: UUID = Field(None, description="UUID of the product")
    commune_uuid: UUID = Field(None, description="UUID of the commune")
    name: str = Field(None, min_length=1, max_length=100, description="Company name")
    description_es: str = Field(None, min_length=1, max_length=100, description="Spanish description")
    description_en: str = Field(None, min_length=1, max_length=100, description="English description")
    address: str = Field(None, min_length=1, max_length=100, description="Physical address")
    phone: str = Field(None, min_length=1, max_length=100, description="Contact phone number")
    email: EmailStr = Field(None, description="Contact email")
    image_url: str = Field(None, min_length=1, max_length=10000, description="Company image URL")


class CompanyResponse(BaseModel):
    """
    Schema for company response with all data.
    NO NULL FIELDS - Everything is required because the database doesn't allow NULLs.
    """
    uuid: UUID
    user_uuid: UUID
    product_uuid: UUID
    commune_uuid: UUID
    name: str
    description_es: str
    description_en: str
    address: str
    phone: str
    email: str
    image_url: str
    created_at: datetime
    updated_at: datetime
    # Joined data from other tables - these are NOT NULL because JOINs will always succeed
    user_name: str
    user_email: str
    product_name_es: str
    product_name_en: str
    commune_name: str

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
    """
    Schema for company search results from materialized view.
    All fields are required - no nulls.
    """
    uuid: UUID
    name: str
    description: str = Field(..., description="Description in requested language")
    address: str
    email: str
    product_name: str = Field(..., description="Product name in requested language")
    commune_name: str
    relevance_score: float = Field(..., description="Search relevance score", ge=0.0)

