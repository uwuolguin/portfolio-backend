import json
import functools
from typing import Callable, Any
from app.cache.redis_client import redis_client
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)


def cache_response(key_prefix: str, ttl: int = None):
    """
    Decorator to cache endpoint responses in Redis
    
    Usage:
        @cache_response(key_prefix="products", ttl=3600)
        async def get_products():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            cache_key = f"{key_prefix}:{json.dumps(kwargs, sort_keys=True)}"
            
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("cache_hit", key=cache_key)
                return json.loads(cached)
            
            logger.debug("cache_miss", key=cache_key)
            result = await func(*args, **kwargs)
            
            expire_time = ttl or settings.cache_ttl
            await redis_client.set(cache_key, json.dumps(result), expire=expire_time)
            
            return result
        
        return wrapper
    return decorator