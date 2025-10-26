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
    Gracefully degrades if Redis is unavailable - just skips caching
    
    Usage:
        @cache_response(key_prefix="products", ttl=3600)
        async def get_products():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not redis_client.is_available():
                logger.debug("cache_skipped_redis_unavailable", func=func.__name__)
                return await func(*args, **kwargs)
            
            cache_key = f"{key_prefix}:{json.dumps(kwargs, sort_keys=True)}"
            
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("cache_hit", key=cache_key)
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    logger.warning("cache_decode_error", key=cache_key)
            
            logger.debug("cache_miss", key=cache_key)
            result = await func(*args, **kwargs)
            
            expire_time = ttl or settings.cache_ttl
            try:
                await redis_client.set(cache_key, json.dumps(result), expire=expire_time)
            except Exception as e:
                logger.warning("cache_set_failed", key=cache_key, error=str(e))
            
            return result
        
        return wrapper
    return decorator