# app/auth/csrf.py
import secrets
from typing import Optional
from fastapi import Request, HTTPException, status
import structlog

logger = structlog.get_logger(__name__)


def generate_csrf_token() -> str:
    """Generate a new CSRF token"""
    return secrets.token_urlsafe(32)


async def get_csrf_token(request: Request) -> str:
    """
    Get CSRF token from cookie or generate new one
    Store in cookie for subsequent requests
    """
    csrf_token = request.cookies.get("csrf_token")
    
    if not csrf_token:
        csrf_token = generate_csrf_token()
    
    return csrf_token


async def validate_csrf_token(request: Request) -> None:
    """
    Validate CSRF token for state-changing operations (POST, PUT, DELETE, PATCH)
    Raises HTTPException if validation fails
    """
    # Skip CSRF for safe methods
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return
    
    # Get token from cookie
    cookie_token = request.cookies.get("csrf_token")
    
    # Get token from header
    header_token = request.headers.get("X-CSRF-Token")
    
    if not cookie_token or not header_token:
        logger.warning("csrf_validation_failed", reason="missing_tokens")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing"
        )
    
    if not secrets.compare_digest(cookie_token, header_token):
        logger.warning("csrf_validation_failed", reason="token_mismatch")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token invalid"
        )
    
    logger.debug("csrf_validation_success")
