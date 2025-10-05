# CHECK SQL INJECTION WHEN YOU MODIFY THIS IN THE FUTURE
import asyncpg
import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List, Dict, Any
from enum import Enum
from uuid import UUID
from app.utils.db_retry import db_retry  # Import it

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
    """Simple database queries - all SQL injection safe with retry logic"""
    
    @staticmethod
    @db_retry()  # Add retry decorator
    async def get_products(conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        async with transaction(conn, readonly=True):
            query = """
                SELECT uuid, name_es, name_en, created_at
                FROM products
                WHERE deleted_at IS NULL
                ORDER BY name_es
            """
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
    
    @staticmethod
    @db_retry()  # Add to all methods
    async def get_product(conn: asyncpg.Connection, product_uuid: UUID) -> Optional[Dict[str, Any]]:
        async with transaction(conn, readonly=True):
            query = """
                SELECT uuid, name_es, name_en, created_at
                FROM products
                WHERE uuid = $1 AND deleted_at IS NULL
            """
            row = await conn.fetchrow(query, product_uuid)
            return dict(row) if row else None
    
    @staticmethod
    @db_retry()
    async def get_communes(conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        async with transaction(conn, readonly=True):
            query = """
                SELECT uuid, name, created_at
                FROM communes
                WHERE deleted_at IS NULL
                ORDER BY name
            """
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
    
    @staticmethod
    @db_retry()
    async def get_companies(
        conn: asyncpg.Connection,
        page: int = 1,
        page_size: int = 10,
        product_uuid: Optional[UUID] = None,
        commune_uuid: Optional[UUID] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        async with transaction(conn, readonly=True):
            where_parts = ["deleted_at IS NULL"]
            params = []
            param_idx = 1
            
            if product_uuid:
                where_parts.append(f"product_uuid = ${param_idx}")
                params.append(product_uuid)
                param_idx += 1
            
            if commune_uuid:
                where_parts.append(f"commune_uuid = ${param_idx}")
                params.append(commune_uuid)
                param_idx += 1
            
            if search:
                where_parts.append(f"name ILIKE ${param_idx}")
                params.append(f"%{search}%")
                param_idx += 1
            
            where_clause = " AND ".join(where_parts)
            
            count_query = f"SELECT COUNT(*) FROM companies WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)
            
            offset = (page - 1) * page_size
            data_query = f"""
                SELECT uuid, name, description_es, description_en,
                       address, phone, email, image_url, 
                       created_at, updated_at
                FROM companies
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([page_size, offset])
            rows = await conn.fetch(data_query, *params)
            
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
    
    @staticmethod
    @db_retry()
    async def create_company(
        conn: asyncpg.Connection,
        user_uuid: UUID,
        product_uuid: UUID,
        commune_uuid: UUID,
        name: str,
        description_es: Optional[str] = None,
        description_en: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        image_url: Optional[str] = None
    ) -> Dict[str, Any]:
        async with transaction(conn):
            # Validate foreign keys
            product_check = await conn.fetchval(
                "SELECT 1 FROM products WHERE uuid = $1 AND deleted_at IS NULL",
                product_uuid
            )
            if not product_check:
                raise ValueError(f"Product {product_uuid} not found")
            
            commune_check = await conn.fetchval(
                "SELECT 1 FROM communes WHERE uuid = $1 AND deleted_at IS NULL",
                commune_uuid
            )
            if not commune_check:
                raise ValueError(f"Commune {commune_uuid} not found")
            
            query = """
                INSERT INTO companies (
                    user_uuid, product_uuid, commune_uuid, name,
                    description_es, description_en, address,
                    phone, email, image_url
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING uuid, name, created_at, updated_at
            """
            row = await conn.fetchrow(
                query,
                user_uuid, product_uuid, commune_uuid, name,
                description_es, description_en, address,
                phone, email, image_url
            )
            logger.info("company_created", company_uuid=str(row["uuid"]))
            return dict(row)
    
    @staticmethod
    @db_retry()
    async def update_company(
        conn: asyncpg.Connection,
        company_uuid: UUID,
        name: Optional[str] = None,
        description_es: Optional[str] = None,
        description_en: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        image_url: Optional[str] = None,
        product_uuid: Optional[UUID] = None,
        commune_uuid: Optional[UUID] = None
    ) -> Optional[Dict[str, Any]]:
        async with transaction(conn):
            updates = {}
            if name is not None:
                updates['name'] = name
            if description_es is not None:
                updates['description_es'] = description_es
            if description_en is not None:
                updates['description_en'] = description_en
            if address is not None:
                updates['address'] = address
            if phone is not None:
                updates['phone'] = phone
            if email is not None:
                updates['email'] = email
            if image_url is not None:
                updates['image_url'] = image_url
            if product_uuid is not None:
                updates['product_uuid'] = product_uuid
            if commune_uuid is not None:
                updates['commune_uuid'] = commune_uuid
            
            if not updates:
                raise ValueError("No fields to update")
            
            set_parts = []
            params = []
            for idx, (field, value) in enumerate(updates.items(), start=1):
                set_parts.append(f"{field} = ${idx}")
                params.append(value)
            
            params.append(company_uuid)
            
            query = f"""
                UPDATE companies
                SET {', '.join(set_parts)}, updated_at = NOW()
                WHERE uuid = ${len(params)} AND deleted_at IS NULL
                RETURNING uuid, name, description_es, description_en,
                         address, phone, email, image_url,
                         created_at, updated_at
            """
            row = await conn.fetchrow(query, *params)
            
            if row:
                logger.info("company_updated", company_uuid=str(company_uuid))
                return dict(row)
            return None
    
    @staticmethod
    @db_retry()
    async def delete_company(conn: asyncpg.Connection, company_uuid: UUID) -> bool:
        async with transaction(conn):
            query = """
                UPDATE companies
                SET deleted_at = NOW(), updated_at = NOW()
                WHERE uuid = $1 AND deleted_at IS NULL
            """
            result = await conn.execute(query, company_uuid)
            rows = int(result.split()[-1])
            
            if rows > 0:
                logger.info("company_deleted", company_uuid=str(company_uuid))
                return True
            return False