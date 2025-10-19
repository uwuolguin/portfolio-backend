from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class CommuneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Commune name (e.g., 'Santiago', 'Valparaíso')")

    model_config = {
        "json_schema_extra": {
            "example": {"name": "Santiago"}
        }
    }

class CommuneUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="New commune name")

    model_config = {
        "json_schema_extra": {
            "example": {"name": "Valparaíso"}
        }
    }

class CommuneResponse(BaseModel):
    uuid: UUID = Field(..., description="Unique identifier for the commune")
    name: str = Field(..., description="Commune name")
    created_at: datetime = Field(..., description="Timestamp when commune was created")

    model_config = {
        "json_schema_extra": {
            "example": {
                "uuid": "a3c1d96b-0a3b-4d53-bb32-9e8e9cf5a71e",
                "name": "Santiago",
                "created_at": "2025-10-19T15:30:00Z"
            }
        }
    }
