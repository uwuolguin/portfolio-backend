from fastapi import HTTPException, status, Request,Depends
from app.auth.jwt import decode_access_token
from app.auth.csrf import validate_csrf_token

async def get_current_user(request: Request) -> dict:
    """
    Get current user from JWT cookie (required - raises exception if not authenticated)
    Use this for protected endpoints
    """
    token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    return payload


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency to require admin role
    Use this for admin-only endpoints
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def require_verified_email(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency to require verified email
    Use this for endpoints that need verified users
    """
    if not current_user.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address to access this resource"
        )
    return current_user


async def verify_csrf(request: Request = None) -> None:
    """
    Dependency to verify CSRF token
    Use this for state-changing endpoints (POST, PUT, DELETE, PATCH)
    """
    if request:
        await validate_csrf_token(request)