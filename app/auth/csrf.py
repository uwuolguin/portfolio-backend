import secrets
from fastapi import Request, HTTPException, status
import structlog

logger = structlog.get_logger(__name__)


def generate_csrf_token() -> str:
    """Generate a new CSRF token"""
    return secrets.token_urlsafe(32)

async def validate_csrf_token(request: Request) -> None:
    """
    Validate CSRF token for state-changing operations (POST, PUT, DELETE, PATCH)
    Raises HTTPException if validation fails
    """
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return

    cookie_token = request.cookies.get("csrf_token")
    
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
