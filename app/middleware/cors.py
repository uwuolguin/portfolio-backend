from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)

def setup_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware with strict settings for demo environment
    """
    allowed_origins = settings.allowed_origins
    
    logger.info(
        "cors_configuration",
        allowed_origins=allowed_origins,
        credentials_allowed=True
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins, 
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"], 
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Correlation-ID",
            "X-CSRF-Token",
            "Accept",
            "Accept-Language",
        ],
        expose_headers=["X-Correlation-ID"],
        max_age=600,
    )