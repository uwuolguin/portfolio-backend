# app/middleware/security.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses
    - X-Frame-Options: Prevent clickjacking
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-XSS-Protection: Enable XSS filter
    - Strict-Transport-Security: Force HTTPS
    - Content-Security-Policy: Control resource loading
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Only add CSP for non-docs routes (docs need external CDN resources)
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
        
        # Only add HSTS in production
        from app.config import settings
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Remove sensitive headers from responses (use del instead of pop)
        if "Server" in response.headers:
            del response.headers["Server"]
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]
        
        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Redirect HTTP to HTTPS in production
    Only active when debug=False
    """
    
    async def dispatch(self, request: Request, call_next):
        from app.config import settings
        
        # Only redirect in production
        if not settings.debug:
            # Check if request is not already HTTPS
            if request.url.scheme != "https":
                # Get forwarded proto header (for reverse proxies)
                forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
                
                if forwarded_proto != "https":
                    url = request.url.replace(scheme="https")
                    logger.warning("https_redirect", original_url=str(request.url), redirect_url=str(url))
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(url=str(url), status_code=301)
        
        return await call_next(request)