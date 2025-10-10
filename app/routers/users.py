from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import asyncpg
from app.database.connection import get_db
from app.database.transactions import DB
from app.schemas.users import UserSignup, UserResponse
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/users",
    tags=["users"]
)


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with email and password"
)
async def signup(
    user_data: UserSignup,
    db: asyncpg.Connection = Depends(get_db)
):
    """
    Register a new user
    
    - **name**: User's full name (2-100 characters)
    - **email**: Valid email address (must be unique)
    - **password**: Strong password (min 8 chars, must include uppercase, lowercase, and digit)
    
    Returns the created user data (without password).
    User must login separately to receive authentication tokens.
    """
    try:
        # Create user in database
        user = await DB.create_user(
            conn=db,
            name=user_data.name,
            email=user_data.email,
            password=user_data.password
        )
        
        logger.info(
            "user_signup_success",
            user_uuid=str(user["uuid"]),
            email=user["email"]
        )
        
        return UserResponse(**user)
        
    except ValueError as e:
        # Handle duplicate email or validation errors
        logger.warning(
            "user_signup_failed",
            email=user_data.email,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Handle unexpected errors
        logger.error(
            "user_signup_error",
            email=user_data.email,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration"
        )
