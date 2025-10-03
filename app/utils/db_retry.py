import logging
import asyncpg
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from app.config import settings

logger = structlog.get_logger(__name__)

TRANSIENT_ERRORS = (
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncpg.exceptions.ConnectionFailureError,
    asyncpg.exceptions.InterfaceError,
    asyncpg.exceptions.InternalServerError,
    asyncpg.exceptions.TooManyConnectionsError,
    asyncpg.exceptions.DeadlockDetectedError,
    asyncpg.exceptions.SerializationError,  
)

def db_retry(
    *, 
    stop_after: int = settings.db_retry_attempts,
    wait_multiplier: float = settings.db_retry_wait_multiplier,
    max_wait: float = settings.db_retry_max_wait,
):
    return retry(
        stop=stop_after_attempt(stop_after),
        wait=wait_exponential(multiplier=wait_multiplier, max=max_wait),
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )