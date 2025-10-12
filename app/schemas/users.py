from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime

class UserSignup(BaseModel):
    """Schema for user registration"""
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=8, max_length=100, description="User's password")
    

class UserResponse(BaseModel):
    """Schema for user response (without password)"""
    uuid: UUID
    name: str
    email: str
    created_at: datetime
    
class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=8, max_length=100, description="User's password")


class LoginResponse(BaseModel):
    """Schema for login response"""
    message: str = Field(..., description="Success message")
    user: dict = Field(..., description="User information")