from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime

class UserSignup(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=1, max_length=100, description="User's password")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Andres Olguin",
                "email": "andres@example.com",
                "password": "strongpassword123"
            }
        }
    }

class UserResponse(BaseModel):
    uuid: UUID
    name: str
    email: str
    created_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "uuid": "4d6f9c3b-ef34-42b8-b2a5-9d4b8e7a12aa",
                "name": "Andres Olguin",
                "email": "andres@example.com",
                "created_at": "2025-10-19T15:30:00Z"
            }
        }
    }

class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=1, max_length=100, description="User's password")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "andres@example.com",
                "password": "strongpassword123"
            }
        }
    }

class LoginResponse(BaseModel):
    message: str = Field(..., description="Success message")
    user: dict = Field(..., description="User information")

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Login successful",
                "user": {
                    "uuid": "4d6f9c3b-ef34-42b8-b2a5-9d4b8e7a12aa",
                    "name": "Andres Olguin",
                    "email": "andres@example.com",
                    "created_at": "2025-10-19T15:30:00Z"
                }
            }
        }
    }

class AdminUserResponse(BaseModel):
    uuid: UUID
    name: str
    email: str
    created_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "uuid": "7bde63f0-5d79-41b3-bd8f-5a23f44dbd94",
                "name": "Admin User",
                "email": "admin@example.com",
                "created_at": "2025-10-19T12:00:00Z"
            }
        }
    }
