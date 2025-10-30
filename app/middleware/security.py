from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import structlog

logger = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Enhanced security headers for demo environment
    Protects against common web vulnerabilities
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        response.headers["X-Frame-Options"] = "DENY"

        response.headers["X-Content-Type-Options"] = "nosniff"
        
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )
        
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "  
                "style-src 'self' 'unsafe-inline'; " 
                "img-src 'self' data: https:; " 
                "font-src 'self'; "
                "connect-src 'self'; "  
                "frame-ancestors 'none'; " 
                "base-uri 'self'; "  
                "form-action 'self'; " 
                "upgrade-insecure-requests;" 
            )
        
        from app.config import settings
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        for header in ["Server", "X-Powered-By", "X-AspNet-Version", "X-AspNetMvc-Version"]:
            if header in response.headers:
                del response.headers[header]
        
        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Force HTTPS in production/demo
    """
    
    async def dispatch(self, request: Request, call_next):
        from app.config import settings
        
        if settings.debug:
            return await call_next(request)
        
        if request.url.scheme == "https":
            return await call_next(request)
        
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
        if forwarded_proto == "https":
            return await call_next(request)
        
        https_url = request.url.replace(scheme="https")
        logger.warning(
            "https_redirect",
            original_url=str(request.url),
            redirect_url=str(https_url),
            client_ip=request.client.host if request.client else None
        )
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=str(https_url), status_code=301)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Basic rate limiting to prevent abuse
    This is a simple in-memory implementation - use Redis for production
    """
    
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_counts = {} 
        
    async def dispatch(self, request: Request, call_next):
        from time import time
        
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"
        
        current_time = time()
        
        if client_ip in self.request_counts:
            self.request_counts[client_ip] = [
                (ts, count) for ts, count in self.request_counts[client_ip]
                if current_time - ts < self.window_seconds
            ]
        else:
            self.request_counts[client_ip] = []
        
        total_requests = sum(count for _, count in self.request_counts[client_ip])
        
        if total_requests >= self.max_requests:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=request.url.path,
                requests=total_requests,
                window=self.window_seconds
            )
            return Response(
                content='{"detail": "Too many requests. Please try again later."}',
                status_code=429,
                media_type="application/json"
            )
        
        self.request_counts[client_ip].append((current_time, 1))
        
        return await call_next(request)