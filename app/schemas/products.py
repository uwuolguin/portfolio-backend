from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional

class ProductCreate(BaseModel):
    name_es: Optional[str] = Field(None, min_length=1, max_length=100, description="Spanish product name (optional if name_en provided)")
    name_en: Optional[str] = Field(None, min_length=1, max_length=100, description="English product name (optional if name_es provided)")

    @model_validator(mode='after')
    def check_at_least_one_name(self):
        if not self.name_es and not self.name_en:
            raise ValueError("At least one product name (name_es or name_en) must be provided")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {"name_es": "Camiseta Roja", "name_en": "Red Shirt"}
        }
    }

class ProductUpdate(BaseModel):
    name_es: Optional[str] = Field(None, min_length=1, max_length=100, description="Spanish product name")
    name_en: Optional[str] = Field(None, min_length=1, max_length=100, description="English product name")

    @model_validator(mode='after')
    def check_at_least_one_name(self):
        if not self.name_es and not self.name_en:
            raise ValueError("At least one product name (name_es or name_en) must be provided")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {"name_es": "Camiseta Azul", "name_en": "Blue Shirt"}
        }
    }

class ProductResponse(BaseModel):
    uuid: UUID
    name_es: str
    name_en: str
    created_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "uuid": "2b7f0b26-38ab-4a9f-8db6-4b2f8f7a24c2",
                "name_es": "Camiseta Roja",
                "name_en": "Red Shirt",
                "created_at": "2025-10-19T15:30:00Z"
            }
        }
    }
