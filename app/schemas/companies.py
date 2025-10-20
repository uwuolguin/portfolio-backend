from pydantic import BaseModel, EmailStr, Field, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


class CompanyCreate(BaseModel):
    product_uuid: UUID = Field(..., description="UUID of the product (required)")
    commune_uuid: UUID = Field(..., description="UUID of the commune (required)")
    name: str = Field(..., min_length=1, max_length=100, description="Company name (required)")
    description_es: Optional[str] = Field(None, min_length=1, max_length=100, description="Spanish description (optional if description_en provided)")
    description_en: Optional[str] = Field(None, min_length=1, max_length=100, description="English description (optional if description_es provided)")
    address: str = Field(..., min_length=1, max_length=100, description="Physical address (required)")
    phone: str = Field(..., min_length=1, max_length=100, description="Contact phone number (required)")
    email: EmailStr = Field(..., description="Contact email (required)")
    image_url: str = Field(..., min_length=1, max_length=10000, description="Company image URL (required)")
    lang: str 

    @model_validator(mode='after')
    def check_at_least_one_description(self):
        if not self.description_es and not self.description_en:
            raise ValueError("At least one description (description_es or description_en) must be provided")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "product_uuid": "3b7e2c5d-87a3-49a0-9a77-24df52a821ac",
                "commune_uuid": "c77b9481-d8c4-4d5e-9b7d-6d7c3e6c239d",
                "name": "Panadería Don Pepe",
                "description_es": "Panadería artesanal con productos frescos cada mañana.",
                "description_en": None,
                "address": "Av. Los Aromos 1234",
                "phone": "+56 9 1234 5678",
                "email": "contacto@donpepe.cl",
                "image_url": "https://example.com/images/panaderia.jpg",
                "lang": "es"}
            }
        }
    


class CompanyUpdate(BaseModel):
    product_uuid: Optional[UUID] = Field(None, description="UUID of the product")
    commune_uuid: Optional[UUID] = Field(None, description="UUID of the commune")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Company name")
    description_es: Optional[str] = Field(None, min_length=1, max_length=100, description="Spanish description")
    description_en: Optional[str] = Field(None, min_length=1, max_length=100, description="English description")
    address: Optional[str] = Field(None, min_length=1, max_length=100, description="Physical address")
    phone: Optional[str] = Field(None, min_length=1, max_length=100, description="Contact phone number")
    email: Optional[EmailStr] = Field(None, description="Contact email")
    image_url: Optional[str] = Field(None, min_length=1, max_length=10000, description="Company image URL")

    @model_validator(mode='after')
    def check_at_least_one_description(self):
        if self.description_es is None and self.description_en is None:
            raise ValueError("At least one description (description_es or description_en) must be provided")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Panadería Don Pepe (actualizada)",
                "description_es": "Nueva descripción en español.",
                "description_en": None,
                "address": "Av. Las Rosas 4321",
                "phone": "+56 9 8765 4321",
                "email": "nuevo@donpepe.cl",
                "image_url": "https://example.com/images/panaderia_nueva.jpg"
            }
        }
    }


class CompanyResponse(BaseModel):
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
    user_name: str
    user_email: str
    product_name_es: str
    product_name_en: str
    commune_name: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "uuid": "f8b123aa-7bc2-4ef2-9208-f4f60a15e512",
                "user_uuid": "e7d5f5a8-51f9-4f6e-b9e9-25a3b24c4d9a",
                "product_uuid": "3b7e2c5d-87a3-49a0-9a77-24df52a821ac",
                "commune_uuid": "c77b9481-d8c4-4d5e-9b7d-6d7c3e6c239d",
                "name": "Panadería Don Pepe",
                "description_es": "Panadería artesanal con productos frescos cada mañana.",
                "description_en": "Artisan bakery offering fresh bread every morning.",
                "address": "Av. Los Aromos 1234",
                "phone": "+56 9 1234 5678",
                "email": "contacto@donpepe.cl",
                "image_url": "https://example.com/images/panaderia.jpg",
                "created_at": "2025-10-19T15:30:00Z",
                "updated_at": "2025-10-19T16:00:00Z",
                "user_name": "Andres Olguin",
                "user_email": "andres@example.com",
                "product_name_es": "Pan Artesanal",
                "product_name_en": "Artisan Bread",
                "commune_name": "Santiago"
            }
        }
    }


class CompanySearchResponse(BaseModel):
    name: str
    description: str = Field(..., description="Description in requested language")
    address: str
    email: str
    phone: str
    img_url: str
    product_name: str = Field(..., description="Product name in requested language")
    commune_name: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Panadería Don Pepe",
                "description": "Panadería artesanal con productos frescos cada mañana.",
                "address": "Av. Los Aromos 1234",
                "email": "contacto@donpepe.cl",
                "phone": "+56 9 1234 5678",
                "img_url": "https://example.com/images/panaderia.jpg",
                "product_name": "Pan Artesanal",
                "commune_name": "Santiago"
            }
        }
    }
