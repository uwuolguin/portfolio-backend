# app/main.py - Complete setup
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.database.connection import init_db_pools, close_db_pools
from app.cache.redis_client import redis_client
from app.middleware.cors import setup_cors
from app.middleware.logging import LoggingMiddleware
from app.middleware.security import SecurityHeadersMiddleware, HTTPSRedirectMiddleware

# Import routers
from app.routers import users, products, communes, companies


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    await init_db_pools()
    await redis_client.connect()
    
    yield
    
    # Shutdown
    await close_db_pools()
    await redis_client.disconnect()


app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    lifespan=lifespan
)

# Setup middleware (ORDER MATTERS!)
# 1. HTTPS redirect (must be first in production)
app.add_middleware(HTTPSRedirectMiddleware)

# 2. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. CORS (must be after security, before logging)
setup_cors(app)

# 4. Logging (should be last to log everything)
app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(users.router, prefix=settings.api_v1_prefix)
app.include_router(products.router, prefix=settings.api_v1_prefix)
app.include_router(communes.router, prefix=settings.api_v1_prefix)
app.include_router(companies.router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root():
    return {"message": "Proveo API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}