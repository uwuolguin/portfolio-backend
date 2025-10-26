import redis.asyncio as redis
from typing import Optional
from app.config import settings
import structlog
import ssl as ssl_module

logger = structlog.get_logger(__name__)


class RedisClient:
    """Redis client manager with graceful degradation"""
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._is_available = False
    
    async def connect(self):
        """Initialize Redis connection - gracefully handles failures"""
        try:
            connection_kwargs = {
                "encoding": "utf-8",
                "decode_responses": True,
                "socket_timeout": settings.redis_timeout,
                "socket_connect_timeout": settings.redis_timeout,
            }
            
            if settings.redis_ssl:
                ssl_context = ssl_module.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl_module.CERT_NONE
                connection_kwargs["ssl"] = ssl_context
            
            self.redis = await redis.from_url(
                settings.redis_url,
                **connection_kwargs
            )
            
            await self.redis.ping()
            self._is_available = True
            logger.info("redis_connected")
            
        except Exception as e:
            self._is_available = False
            self.redis = None
            logger.warning(
                "redis_connection_failed_continuing_without_cache",
                error=str(e),
                message="Application will run without caching"
            )
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            try:
                await self.redis.close()
                logger.info("redis_disconnected")
            except Exception as e:
                logger.warning("redis_disconnect_error", error=str(e))
        self._is_available = False
    
    def is_available(self) -> bool:
        """Check if Redis is available"""
        return self._is_available
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis - returns None if Redis unavailable"""
        if not self._is_available or not self.redis:
            return None
            
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.warning("redis_get_failed", key=key, error=str(e))
            self._is_available = False
            return None
    
    async def set(self, key: str, value: str, expire: int = None) -> bool:
        """Set value in Redis - returns False if Redis unavailable"""
        if not self._is_available or not self.redis:
            return False
            
        try:
            if expire:
                result = await self.redis.setex(key, expire, value)
            else:
                result = await self.redis.set(key, value)
            return bool(result)
        except Exception as e:
            logger.warning("redis_set_failed", key=key, error=str(e))
            self._is_available = False
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis - returns False if Redis unavailable"""
        if not self._is_available or not self.redis:
            return False
            
        try:
            return await self.redis.delete(key) > 0
        except Exception as e:
            logger.warning("redis_delete_failed", key=key, error=str(e))
            self._is_available = False
            return False


redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """Dependency to get Redis client"""
    return redis_client