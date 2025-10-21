from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings


def setup_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware
    Controls cross-origin requests and sets allowed origins, methods, headers
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Correlation-ID",
            "X-CSRF-Token"
        ],
        expose_headers=["X-Correlation-ID"],
        max_age=600,  
    )
