import asyncpg
import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List, Dict, Any
from enum import Enum
from uuid import UUID
from app.utils.db_retry import db_retry
from app.auth.jwt import get_password_hash
from app.config import settings
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
        async with transaction(conn):
            existing = await conn.fetchval(
                "SELECT 1 FROM fastapi.users WHERE email = $1",
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
            logger.info("user_created", user_uuid=str(row["uuid"]), email=email)
            return dict(row)

    @staticmethod
    @db_retry()
    async def get_user_by_email(
        conn: asyncpg.Connection,
        email: str
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT uuid, name, email, hashed_password, created_at
            FROM fastapi.users
            WHERE email = $1
        """
        row = await conn.fetchrow(query, email)
        return dict(row) if row else None

    @staticmethod
    @db_retry()
    async def delete_user_by_uuid(
        conn: asyncpg.Connection,
        user_uuid: UUID
    ) -> Dict[str, Any]:
        async with transaction(conn, isolation=IsolationLevel.SERIALIZABLE):
            user_query = """
                SELECT uuid, name, email, hashed_password, created_at
                FROM fastapi.users
                WHERE uuid = $1
            """
            user = await conn.fetchrow(user_query, user_uuid)
            if not user:
                raise ValueError(f"User with UUID {user_uuid} not found")
            companies_query = """
                SELECT uuid, user_uuid, product_uuid, commune_uuid, name, 
                       description_es, description_en, address, phone, email, 
                       image_url, created_at, updated_at
                FROM fastapi.companies
                WHERE user_uuid = $1
            """
            companies = await conn.fetch(companies_query, user_uuid)
            if companies:
                delete_companies_query = """
                    INSERT INTO fastapi.companies_deleted 
                        (uuid, user_uuid, product_uuid, commune_uuid, name, 
                         description_es, description_en, address, phone, email, 
                         image_url, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """
                for company in companies:
                    await conn.execute(
                        delete_companies_query,
                        company["uuid"], company["user_uuid"], company["product_uuid"],
                        company["commune_uuid"], company["name"], company["description_es"],
                        company["description_en"], company["address"], company["phone"],
                        company["email"], company["image_url"], company["created_at"],
                        company["updated_at"]
                    )
                await conn.execute(
                    "DELETE FROM fastapi.companies WHERE user_uuid = $1",
                    user_uuid
                )
                logger.info(
                    "user_companies_deleted",
                    user_uuid=str(user_uuid),
                    companies_count=len(companies)
                )
            insert_deleted_user = """
                INSERT INTO fastapi.users_deleted (uuid, name, email, hashed_password, created_at)
                VALUES ($1, $2, $3, $4, $5)
            """
            await conn.execute(
                insert_deleted_user,
                user["uuid"], user["name"], user["email"],
                user["hashed_password"], user["created_at"]
            )
            await conn.execute("DELETE FROM fastapi.users WHERE uuid = $1", user_uuid)
            logger.info(
                "user_deleted_with_cascade",
                user_uuid=str(user_uuid),
                email=user["email"],
                companies_deleted=len(companies)
            )
            return {
                "user_uuid": str(user_uuid),
                "email": user["email"],
                "companies_deleted": len(companies)
            }

    @staticmethod
    @db_retry()
    async def delete_company_by_uuid(
        conn: asyncpg.Connection,
        company_uuid: UUID,
        user_uuid: UUID
    ) -> bool:
        async with transaction(conn):
            company_query = """
                SELECT uuid, user_uuid, product_uuid, commune_uuid, name,
                       description_es, description_en, address, phone, email,
                       image_url, created_at, updated_at
                FROM fastapi.companies
                WHERE uuid = $1 AND user_uuid = $2
            """
            company = await conn.fetchrow(company_query, company_uuid, user_uuid)
            if not company:
                logger.warning(
                    "company_delete_failed",
                    company_uuid=str(company_uuid),
                    user_uuid=str(user_uuid),
                    reason="not_found_or_not_owned"
                )
                return False
            insert_deleted = """
                INSERT INTO fastapi.companies_deleted
                    (uuid, user_uuid, product_uuid, commune_uuid, name,
                     description_es, description_en, address, phone, email,
                     image_url, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """
            await conn.execute(
                insert_deleted,
                company["uuid"], company["user_uuid"], company["product_uuid"],
                company["commune_uuid"], company["name"], company["description_es"],
                company["description_en"], company["address"], company["phone"],
                company["email"], company["image_url"], company["created_at"],
                company["updated_at"]
            )
            await conn.execute("DELETE FROM fastapi.companies WHERE uuid = $1", company_uuid)
            logger.info("company_deleted", company_uuid=str(company_uuid))
            return True

    @staticmethod
    def is_admin(email: str) -> bool:
        return email.lower() == settings.admin_email.lower()

    @staticmethod
    @db_retry()
    async def delete_product_by_uuid(
        conn: asyncpg.Connection,
        product_uuid: UUID,
        user_email: str
    ) -> Dict[str, Any]:
        if not DB.is_admin(user_email):
            raise PermissionError(
                "Only admin users can delete products. "
                "Contact acos2014600836@gmail.com for assistance."
            )
        async with transaction(conn, isolation=IsolationLevel.SERIALIZABLE):
            product_query = """
                SELECT uuid, name_es, name_en, created_at
                FROM fastapi.products
                WHERE uuid = $1
            """
            product = await conn.fetchrow(product_query, product_uuid)
            if not product:
                raise ValueError(f"Product with UUID {product_uuid} not found")
            company_count = await conn.fetchval(
                "SELECT COUNT(*) FROM fastapi.companies WHERE product_uuid = $1",
                product_uuid
            )
            if company_count > 0:
                raise ValueError(
                    f"Cannot delete product '{product['name_en']}'. "
                    f"{company_count} company(ies) are still using this product."
                )
            insert_deleted = """
                INSERT INTO fastapi.products_deleted (uuid, name_es, name_en, created_at)
                VALUES ($1, $2, $3, $4)
            """
            await conn.execute(
                insert_deleted,
                product["uuid"], product["name_es"], product["name_en"], product["created_at"]
            )
            await conn.execute("DELETE FROM fastapi.products WHERE uuid = $1", product_uuid)
            logger.info("product_deleted", product_uuid=str(product_uuid))
            return {
                "uuid": str(product["uuid"]),
                "name_es": product["name_es"],
                "name_en": product["name_en"]
            }

    @staticmethod
    @db_retry()
    async def delete_commune_by_uuid(
        conn: asyncpg.Connection,
        commune_uuid: UUID,
        user_email: str
    ) -> Dict[str, Any]:
        if not DB.is_admin(user_email):
            raise PermissionError(
                "Only admin users can delete communes. "
                "Contact acos2014600836@gmail.com for assistance."
            )
        async with transaction(conn, isolation=IsolationLevel.SERIALIZABLE):
            commune_query = """
                SELECT uuid, name, created_at
                FROM fastapi.communes
                WHERE uuid = $1
            """
            commune = await conn.fetchrow(commune_query, commune_uuid)
            if not commune:
                raise ValueError(f"Commune with UUID {commune_uuid} not found")
            company_count = await conn.fetchval(
                "SELECT COUNT(*) FROM fastapi.companies WHERE commune_uuid = $1",
                commune_uuid
            )
            if company_count > 0:
                raise ValueError(
                    f"Cannot delete commune '{commune['name']}'. "
                    f"{company_count} company(ies) are still located in this commune."
                )
            insert_deleted = """
                INSERT INTO fastapi.communes_deleted (uuid, name, created_at)
                VALUES ($1, $2, $3)
            """
            await conn.execute(
                insert_deleted,
                commune["uuid"], commune["name"], commune["created_at"]
            )
            await conn.execute("DELETE FROM fastapi.communes WHERE uuid = $1", commune_uuid)
            logger.info("commune_deleted", commune_uuid=str(commune_uuid))
            return {
                "uuid": str(commune["uuid"]),
                "name": commune["name"]
            }
