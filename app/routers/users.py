from fastapi import APIRouter, Depends, HTTPException, status, Response, Request,Query
from typing import List
import asyncpg
from datetime import timedelta
from app.database.connection import get_db
from app.database.transactions import DB
from app.schemas.users import UserSignup, UserResponse, UserLogin, LoginResponse, AdminUserResponse
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
@router.get(
    "/admin/all-users/use-postman-or-similar-to-send-csrf",
    response_model=List[AdminUserResponse],
    summary="Get all users (Admin Only)",
    description="Retrieve all users in the database with their company count - admin authentication required"
)
async def get_all_users(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Get all users with their company count - admin only"""
    try:
        # Check if user is admin
        if not DB.is_admin(current_user["email"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can view all users"
            )
        
        users = await DB.get_all_users_with_company_count(
            conn=db,
            limit=limit,
            offset=offset
        )
        
        logger.info(
            "admin_get_all_users",
            admin_email=current_user["email"],
            users_count=len(users)
        )
        
        return [AdminUserResponse(**user) for user in users]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_all_users_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )


@router.delete(
    "/admin/users/{user_uuid}/use-postman-or-similar-to-send-csrf",
    status_code=status.HTTP_200_OK,
    summary="Delete any user by UUID (Admin Only)",
    description="Admin can delete any user and all their companies - requires admin authentication"
)
async def admin_delete_user(
    user_uuid: UUID,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_csrf)
):
    """
    Delete any user - admin only.
    
    This endpoint allows admins to delete any user account and all their companies.
    The user and companies are moved to deleted tables before removal.
    
    Process:
    1. Verify user is admin
    2. Check if target user exists
    3. Archive and delete all user's companies
    4. Archive and delete the user
    5. Refresh materialized view
    
    Returns:
        Success message with deleted user info
    
    Raises:
        403: User is not admin
        404: Target user not found
        400: Cannot delete yourself as admin
        500: Database error
    """
    try:
        # Check if user is admin
        if not DB.is_admin(current_user["email"]):
            logger.warning(
                "admin_delete_user_unauthorized",
                user_uuid=str(user_uuid),
                requesting_user=current_user["email"]
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can delete other users"
            )
        
        # Prevent admin from deleting themselves
        if str(user_uuid) == current_user["sub"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own admin account. Use /users/me endpoint instead."
            )
        
        result = await DB.admin_delete_user_by_uuid(
            conn=db,
            user_uuid=user_uuid,
            admin_email=current_user["email"]
        )
        
        # Refresh materialized view if companies were deleted
        if result["companies_deleted"] > 0:
            await db.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
        
        logger.info(
            "admin_deleted_user_successfully",
            deleted_user_uuid=str(user_uuid),
            deleted_user_email=result["email"],
            companies_deleted=result["companies_deleted"],
            admin_email=current_user["email"]
        )
        
        return {
            "message": "User and all associated companies successfully deleted",
            "user_uuid": result["user_uuid"],
            "email": result["email"],
            "companies_deleted": result["companies_deleted"]
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "admin_delete_user_error",
            user_uuid=str(user_uuid),
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )