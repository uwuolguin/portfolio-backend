"""
Cache invalidation helper - call this after DB changes
Makes cache management brain-dead simple
"""
import structlog
from app.cache.redis_client import redis_client

logger = structlog.get_logger(__name__)


class CacheManager:
    """Handles all cache invalidation logic"""
    
    # Cache key patterns
    PRODUCTS_KEY = "products:all:{}"
    COMMUNES_KEY = "communes:all:{}"
    
    @staticmethod
    async def invalidate_products():
        """Clear products cache after admin creates/updates/deletes product"""
        try:
            deleted = await redis_client.delete(CacheManager.PRODUCTS_KEY)
            if deleted:
                logger.info("cache_invalidated", key="products:all")
            return True
        except Exception as e:
            logger.warning("cache_invalidation_failed", key="products", error=str(e))
            return False
    
    @staticmethod
    async def invalidate_communes():
        """Clear communes cache after admin creates/updates/deletes commune"""
        try:
            deleted = await redis_client.delete(CacheManager.COMMUNES_KEY)
            if deleted:
                logger.info("cache_invalidated", key="communes:all")
            return True
        except Exception as e:
            logger.warning("cache_invalidation_failed", key="communes", error=str(e))
            return False
    
    @staticmethod
    async def invalidate_all():
        """Nuclear option - clear everything (use for emergencies)"""
        try:
            if not redis_client.is_available() or not redis_client.redis:
                return False
                
            await redis_client.redis.flushdb()
            logger.warning("cache_nuked", message="All cache cleared")
            return True
        except Exception as e:
            logger.error("cache_nuke_failed", error=str(e))
            return False



cache_manager = CacheManager()