from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from typing import List
import asyncpg
from datetime import timedelta
from app.database.connection import get_db
from app.database.transactions import DB
from app.schemas.users import UserSignup, UserResponse, UserLogin, LoginResponse
from app.auth.jwt import verify_password, create_access_token
from app.auth.csrf import generate_csrf_token
from app.auth.dependencies import get_current_user, verify_csrf
from app.config import settings
import structlog
from uuid import UUID

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
    try:
        user = await DB.create_user(
            conn=db,
            name=user_data.name,
            email=user_data.email,
            password=user_data.password
        )
        return UserResponse(**user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error("signup_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during signup"
        )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login user and receive JWT/CSRF tokens",
    description="Authenticate user with email/password and set secure HTTP-only JWT and CSRF cookies"
)
async def login(
    user_data: UserLogin,
    response: Response,
    db: asyncpg.Connection = Depends(get_db)
):
    user = await DB.get_user_by_email(conn=db, email=user_data.email)
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        logger.warning("login_failed", email=user_data.email, reason="invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    jwt_payload = {
        "sub": str(user["uuid"]),
        "name": user["name"],
        "email": user["email"],
        "created_at": user["created_at"].isoformat()
    }
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data=jwt_payload, expires_delta=access_token_expires
    )
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        expires=int(access_token_expires.total_seconds())
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=not settings.debug,
        samesite="lax",
        expires=int(access_token_expires.total_seconds())
    )
    logger.info("login_success", user_uuid=str(user["uuid"]))
    return LoginResponse(
        message="Login successful",
        csrf_token=csrf_token,
        user={"email": user["email"]}
    )


@router.post(
    "/logout",
    summary="Logout user",
    description="Clear JWT and CSRF cookies"
)
async def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=not settings.debug,
        samesite="lax"
    )
    response.delete_cookie(
        key="csrf_token",
        httponly=False,
        secure=not settings.debug,
        samesite="lax"
    )
    logger.info("logout_success")
    return {"message": "Logout successful"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get information about the currently authenticated user"
)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user)
):
    logger.info("get_current_user", user_uuid=current_user.get("sub"))
    return UserResponse(
        uuid=current_user["sub"],
        name=current_user["name"],
        email=current_user["email"],
        created_at=current_user["created_at"]
    )


@router.delete(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Delete the current user account",
    description="Permanently delete the currently authenticated user's account and all associated companies"
)
async def delete_me(
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    user_uuid = current_user["sub"]
    user_email = current_user["email"]
    try:
        result = await DB.delete_user_by_uuid(conn=db, user_uuid=UUID(user_uuid))
        response.delete_cookie(
            key="access_token",
            httponly=True,
            secure=not settings.debug,
            samesite="lax"
        )
        response.delete_cookie(
            key="csrf_token",
            httponly=False,
            secure=not settings.debug,
            samesite="lax"
        )
        logger.info(
            "user_account_deleted_with_companies",
            user_uuid=user_uuid,
            email=user_email,
            companies_deleted=result["companies_deleted"]
        )
        return {
            "message": "User account and all associated data successfully deleted",
            "companies_deleted": result["companies_deleted"]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("user_deletion_error", user_uuid=user_uuid, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user account"
        )