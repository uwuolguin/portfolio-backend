from fastapi import Request
import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Enhanced logging with security-focused information
    """
    
    # Paths to exclude from logging (reduce noise)
    EXCLUDE_PATHS = {"/health", "/favicon.ico"}
    
    # Sensitive headers to redact from logs
    SENSITIVE_HEADERS = {
        "authorization",
        "cookie",
        "x-csrf-token",
        "x-api-key",
    }
    
    async def dispatch(self, request: Request, call_next):
        # Skip logging for excluded paths
        if request.url.path in self.EXCLUDE_PATHS:
            return await call_next(request)
        
        # Generate correlation ID
        correlation_id = request.headers.get(
            "X-Correlation-ID",
            f"req_{int(time.time() * 1000)}"
        )
        
        # Get client information
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"
        
        real_ip = request.headers.get("X-Real-IP", client_ip)
        user_agent = request.headers.get("user-agent", "unknown")
        
        start_time = time.time()
        
        # Log request start with security context
        logger.info(
            "request_started",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params) if request.query_params else None,
            client_ip=client_ip,
            real_ip=real_ip,
            user_agent=user_agent,
            referer=request.headers.get("referer"),
            content_type=request.headers.get("content-type"),
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Determine log level based on status code
        log_level = "info"
        if response.status_code >= 500:
            log_level = "error"
        elif response.status_code >= 400:
            log_level = "warning"
        
        # Log response with security indicators
        getattr(logger, log_level)(
            "request_completed",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=f"{duration * 1000:.2f}",
            client_ip=client_ip,
            real_ip=real_ip,
            response_size=response.headers.get("content-length", "unknown"),
            
            # Security indicators
            suspicious_path=self._is_suspicious_path(request.url.path),
            unusual_method=request.method not in ["GET", "POST", "PUT", "DELETE", "PATCH"],
            high_duration=duration > 5.0,
        )
        
        # Set correlation ID in response
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response
    
    @staticmethod
    def _is_suspicious_path(path: str) -> bool:
        """
        Detect common attack patterns in URL paths
        """
        suspicious_patterns = [
            "..", "~", "/etc/", "/proc/", "/sys/",
            "eval(", "exec(", "system(", "<script",
            "SELECT", "UNION", "DROP", "INSERT",
            ".php", ".asp", ".jsp", ".cgi",
            "wp-admin", "wp-login", "phpmyadmin",
        ]
        
        path_lower = path.lower()
        return any(pattern.lower() in path_lower for pattern in suspicious_patterns)