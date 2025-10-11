import asyncpg
import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List, Dict, Any
from enum import Enum
from uuid import UUID
from app.utils.db_retry import db_retry 
from app.auth.jwt import get_password_hash
import uuid

logger = structlog.get_logger(__name__)


class IsolationLevel(Enum):
    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"


@asynccontextmanager
async def transaction(
    conn: asyncpg.Connection,
    isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    readonly: bool = False
) -> AsyncGenerator[asyncpg.Connection, None]:
    options = [f"ISOLATION LEVEL {isolation.value}"]
    if readonly:
        options.append("READ ONLY")
    tx_sql = f"BEGIN {' '.join(options)}"
    try:
        await conn.execute(tx_sql)
        logger.debug("transaction_started", isolation=isolation.value, readonly=readonly)
        yield conn
        await conn.execute("COMMIT")
        logger.debug("transaction_committed")
    except Exception as e:
        await conn.execute("ROLLBACK")
        logger.warning("transaction_rolled_back", error=str(e), error_type=type(e).__name__)
        raise


class DB:

    @staticmethod
    @db_retry()
    async def create_user(
        conn: asyncpg.Connection,
        name: str,
        email: str,
        password: str
    ) -> Dict[str, Any]:
        """
        Create a new user with hashed password
        Validates email uniqueness before insertion
        """
        async with transaction(conn):
            existing = await conn.fetchval(
                """
                SELECT 1 FROM fastapi.users 
                WHERE email = $1
                """,
                email
            )
            
            if existing:
                raise ValueError(f"Email {email} is already registered")
            
            hashed_password = get_password_hash(password)
            
            user_uuid = str(uuid.uuid4())

            query = """
                INSERT INTO fastapi.users (uuid, name, email, hashed_password)
                VALUES ($1, $2, $3, $4)
                RETURNING uuid, name, email, created_at
            """
            
            row = await conn.fetchrow(query, user_uuid, name, email, hashed_password)
            
            logger.info(
                "user_created",
                user_uuid=str(row["uuid"]),
                email=email
            )
            
            return dict(row)
