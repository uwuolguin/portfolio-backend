# app/cache/redis_client.py
import redis.asyncio as redis
from typing import Optional
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)


class RedisClient:
    """Redis client manager"""
    
    def __init__(self):
        self.redis: redis.Redis = None
    
    async def connect(self):
        """Initialize Redis connection"""
        try:
            self.redis = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=settings.redis_timeout,
                socket_connect_timeout=settings.redis_timeout,
                ssl=settings.redis_ssl
            )
            await self.redis.ping()
            logger.info("redis_connected")
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("redis_disconnected")
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        return await self.redis.get(key)
    
    async def set(self, key: str, value: str, expire: int = None) -> bool:
        """Set value in Redis with optional expiration"""
        if expire:
            return await self.redis.setex(key, expire, value)
        return await self.redis.set(key, value)
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis"""
        return await self.redis.delete(key) > 0


redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """Dependency to get Redis client"""
    return redis_client
