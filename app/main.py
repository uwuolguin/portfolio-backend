from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.database.connection import init_db_pools, close_db_pools
from app.cache.redis_client import redis_client
from app.middleware.cors import setup_cors
from app.middleware.logging import LoggingMiddleware
from app.middleware.security import SecurityHeadersMiddleware, HTTPSRedirectMiddleware

from app.routers import users, products, communes, companies


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pools()
    await redis_client.connect()
    
    yield
    
    await close_db_pools()
    await redis_client.disconnect()


app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(SecurityHeadersMiddleware)

setup_cors(app)

app.add_middleware(LoggingMiddleware)

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