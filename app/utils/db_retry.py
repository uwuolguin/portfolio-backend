import asyncpg
import structlog
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    before_sleep_log
)
from typing import Callable, Any, TypeVar, Awaitable
from app.config import settings

logger = structlog.get_logger()
T = TypeVar('T')

# Transient errors that should be retried
TRANSIENT_ERRORS = (
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncpg.exceptions.ConnectionFailureError,
    asyncpg.exceptions.InterfaceError,
    asyncpg.exceptions.InternalServerError,
    asyncpg.exceptions.TooManyConnectionsError,
    # Deadlock and serialization failures
    asyncpg.exceptions.DeadlockDetectedError,
    asyncpg.exceptions.SerializationFailureError,
)

def db_retry(
    stop_after: int = settings.db_retry_attempts,
    wait_multiplier: float = settings.db_retry_wait_multiplier,
    max_wait: float = settings.db_retry_max_wait
):
    """Decorator for database operations with retry logic"""
    return retry(
        stop=stop_after_attempt(stop_after),
        wait=wait_exponential(multiplier=wait_multiplier, max=max_wait),
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )

async def execute_with_retry(
    operation: Callable[..., Awaitable[T]], 
    *args, 
    **kwargs
) -> T:
    """Execute database operation with automatic retry"""
    
    @db_retry()
    async def _execute():
        return await operation(*args, **kwargs)
    
    try:
        return await _execute()
    except TRANSIENT_ERRORS as e:
        logger.error("Database operation failed after retries", 
                    operation=operation.__name__, error=str(e))
        raise
    except Exception as e:
        logger.error("Database operation failed with non-retryable error", 
                    operation=operation.__name__, error=str(e))
        raise
