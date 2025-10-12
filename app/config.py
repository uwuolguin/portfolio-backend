# app/config.py - Updated
from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    # Database Connection & Pool Configuration
    database_url: str
    alembic_database_url: str
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20
    db_pool_max_queries: int = 50000
    db_pool_max_inactive: float = 300.0
    db_timeout: int = 30
    db_command_timeout: int = 60
    db_server_timeout: int = 60
    
    # Database SSL/TLS
    db_ssl_mode: str = "require"
    db_ssl_cert_path: Optional[str] = None
    db_ssl_key_path: Optional[str] = None

    # Redis
    redis_url: str
    redis_timeout: int = 5
    cache_ttl: int = 3600
    redis_ssl: bool = False
    
    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    
    # Content Moderation
    enable_content_moderation: bool = True
    max_file_size: int = 10_000_000
    allowed_file_types: List[str] = ["image/jpeg", "image/png", "image/webp"]
    
    # API
    api_v1_prefix: str = "/api/v1"
    project_name: str = "Proveo API"
    debug: bool = False
    
    # CORS
    allowed_origins: List[str] = ["http://localhost:3000"]
    
    # Database Monitoring & Health
    db_health_check_interval: int = 30
    db_slow_query_threshold: float = 1.0
    
    # Retry Configuration
    db_retry_attempts: int = 3
    db_retry_wait_multiplier: float = 0.5
    db_retry_max_wait: float = 5.0
    
    class Config:
        env_file = ".env"

settings = Settings()
