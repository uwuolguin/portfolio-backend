from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from typing import List
import asyncpg
from datetime import timedelta
from uuid import UUID
from app.database.connection import get_db
from app.database.transactions import DB
from app.schemas.users import UserSignup, UserResponse, UserLogin, LoginResponse, AdminUserResponse
from app.auth.jwt import verify_password, create_access_token
from app.auth.csrf import generate_csrf_token
from app.auth.dependencies import get_current_user, verify_csrf, require_admin
from app.services.email import email_service
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserSignup, db: asyncpg.Connection = Depends(get_db)):
    try:
        user = await DB.create_user(
            conn=db, 
            name=user_data.name, 
            email=user_data.email, 
            password=user_data.password
        )
        
        # Send verification email (don't block signup if email fails)
        verification_token = user.get('verification_token')
        if verification_token:
            await email_service.send_verification_email(
                to_email=user['email'],
                token=verification_token,
                user_name=user['name']
            )
        
        # Remove token from response
        user.pop('verification_token', None)
        
        return UserResponse(**user)
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error("signup_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An unexpected error occurred during signup"
        )


@router.get("/verify-email/{token}")
async def verify_email(token: str, db: asyncpg.Connection = Depends(get_db)):
    """Verify user email with token from email link"""
    try:
        user = await DB.verify_email(conn=db, token=token)
        return {
            "message": "✅ Email verified successfully! You can now log in.",
            "email": user['email']
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("email_verification_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify email"
        )


@router.post("/resend-verification")
async def resend_verification(email: str, db: asyncpg.Connection = Depends(get_db)):
    """Resend verification email"""
    try:
        user = await DB.resend_verification_email(conn=db, email=email)
        
        verification_token = user.get('verification_token')
        if verification_token:
            await email_service.send_verification_email(
                to_email=user['email'],
                token=verification_token,
                user_name=user['name']
            )
        
        return {
            "message": "Verification email sent. Please check your inbox."
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("resend_verification_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email"
        )


@router.post("/login", response_model=LoginResponse)
async def login(user_data: UserLogin, response: Response, db: asyncpg.Connection = Depends(get_db)):
    user = await DB.get_user_by_email(conn=db, email=user_data.email)
    
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        logger.warning("login_failed", email=user_data.email, reason="invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Incorrect email or password"
        )
    
    # Include role and email_verified in JWT
    jwt_payload = {
        "sub": str(user["uuid"]),
        "name": user["name"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "email_verified": user.get("email_verified", False),
        "created_at": user["created_at"].isoformat()
    }
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(data=jwt_payload, expires_delta=access_token_expires)
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
    
    logger.info("login_success", user_uuid=str(user["uuid"]), email_verified=user.get("email_verified"))
    
    return LoginResponse(
        message="Login successful",
        csrf_token=csrf_token,
        user={
            "email": user["email"],
            "email_verified": user.get("email_verified", False)
        }
    )


@router.post("/logout")
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


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    logger.info("get_current_user", user_uuid=current_user.get("sub"))
    return UserResponse(
        uuid=current_user["sub"], 
        name=current_user["name"], 
        email=current_user["email"],
        role=current_user.get("role", "user"),
        email_verified=current_user.get("email_verified", False),
        created_at=current_user["created_at"]
    )


@router.delete("/me", status_code=status.HTTP_200_OK)
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
        
        logger.info("user_account_deleted_with_companies", 
                   user_uuid=user_uuid, 
                   email=user_email, 
                   companies_deleted=result["companies_deleted"])
        
        return {
            "message": "User account and all associated data successfully deleted",
            "companies_deleted": result["companies_deleted"]
        }
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("user_deletion_error", user_uuid=user_uuid, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to delete user account"
        )


@router.get("/admin/all-users/use-postman-or-similar-to-send-csrf", response_model=List[AdminUserResponse])
async def get_all_users(
    limit: int = Query(100, ge=1, le=500), 
    offset: int = Query(0, ge=0), 
    current_user: dict = Depends(require_admin),  # ← Changed!
    db: asyncpg.Connection = Depends(get_db)
):
    try:
        users = await DB.get_all_users_with_company_count(conn=db, limit=limit, offset=offset)
        logger.info("admin_get_all_users", admin_email=current_user["email"], users_count=len(users))
        return [AdminUserResponse(**user) for user in users]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_all_users_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to retrieve users"
        )


@router.delete("/admin/users/{user_uuid}/use-postman-or-similar-to-send-csrf", status_code=status.HTTP_200_OK)
async def admin_delete_user(
    user_uuid: UUID, 
    current_user: dict = Depends(require_admin),  # ← Changed!
    db: asyncpg.Connection = Depends(get_db), 
    _: None = Depends(verify_csrf)
):
    try:
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
        
        logger.info("admin_deleted_user_successfully", 
                   deleted_user_uuid=str(user_uuid), 
                   deleted_user_email=result["email"], 
                   companies_deleted=result["companies_deleted"], 
                   admin_email=current_user["email"])
        
        return {
            "message": "User and all associated companies successfully deleted",
            "user_uuid": result["user_uuid"],
            "email": result["email"],
            "companies_deleted": result["companies_deleted"]
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("admin_delete_user_error", user_uuid=str(user_uuid), error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to delete user"
        )