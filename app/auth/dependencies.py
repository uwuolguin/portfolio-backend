from fastapi import Depends, HTTPException, status, Request
from typing import Optional
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


async def verify_csrf(request: Request = None) -> None:
    """
    Dependency to verify CSRF token
    Use this for state-changing endpoints (POST, PUT, DELETE, PATCH)
    """
    if request:
        await validate_csrf_token(request)