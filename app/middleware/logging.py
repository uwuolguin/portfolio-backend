from fastapi import Request
import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and status"""
    
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", f"req_{int(time.time() * 1000)}")
        
        start_time = time.time()
        
        logger.info(
            "request_started",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "unknown")
        )
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        
        log_level = "info" if response.status_code < 400 else "warning" if response.status_code < 500 else "error"
        getattr(logger, log_level)(
            "request_completed",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=f"{duration * 1000:.2f}"
        )
        
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response
