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
    # ============================================================================
    # USER OPERATIONS
    # ============================================================================
    
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
                
                # REFRESH MATERIALIZED VIEW - companies were deleted
                await conn.execute("REFRESH MATERIALIZED VIEW fastapi.company_search")
                
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
    async def get_all_users_with_company_count(
        conn: asyncpg.Connection,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all users with their company count - admin only.
        
        Args:
            conn: Database connection
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of user dictionaries with company_count field
        """
        query = """
            SELECT 
                u.uuid,
                u.name,
                u.email,
                u.created_at,
                COUNT(c.uuid) as company_count
            FROM fastapi.users u
            LEFT JOIN fastapi.companies c ON c.user_uuid = u.uuid
            GROUP BY u.uuid, u.name, u.email, u.created_at
            ORDER BY u.created_at DESC
            LIMIT $1 OFFSET $2
        """
        rows = await conn.fetch(query, limit, offset)
        return [dict(row) for row in rows]

    @staticmethod
    @db_retry()
    async def admin_delete_user_by_uuid(
        conn: asyncpg.Connection,
        user_uuid: UUID,
        admin_email: str
    ) -> Dict[str, Any]:
        """
        Admin can delete any user and cascade delete their companies.
        
        This is similar to delete_user_by_uuid but requires admin permissions
        and can delete any user (not just the current user).
        
        Args:
            conn: Database connection
            user_uuid: UUID of user to delete
            admin_email: Email of admin performing the deletion
            
        Returns:
            Dictionary with deleted user info and companies count
            
        Raises:
            PermissionError: If user is not admin
            ValueError: If user not found
        """
        if not DB.is_admin(admin_email):
            raise PermissionError(
                "Only admin users can delete other users. "
                "Contact acos2014600836@gmail.com for assistance."
            )
        
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
                    "admin_deleted_user_companies",
                    user_uuid=str(user_uuid),
                    companies_count=len(companies),
                    admin_email=admin_email
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
                "admin_deleted_user_with_cascade",
                deleted_user_uuid=str(user_uuid),
                deleted_user_email=user["email"],
                companies_deleted=len(companies),
                admin_email=admin_email
            )
            
            return {
                "user_uuid": str(user_uuid),
                "email": user["email"],
                "companies_deleted": len(companies)
            }

    # ============================================================================
    # PRODUCT OPERATIONS
    # ============================================================================
    
    @staticmethod
    @db_retry()
    async def get_all_products(
        conn: asyncpg.Connection,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT uuid, name_es, name_en, created_at
            FROM fastapi.products
            ORDER BY name_en ASC
            LIMIT $1 OFFSET $2
        """
        rows = await conn.fetch(query, limit, offset)
        return [dict(row) for row in rows]

    @staticmethod
    @db_retry()
    async def get_product_by_uuid(
        conn: asyncpg.Connection,
        product_uuid: UUID
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT uuid, name_es, name_en, created_at
            FROM fastapi.products
            WHERE uuid = $1
        """
        row = await conn.fetchrow(query, product_uuid)
        return dict(row) if row else None

    @staticmethod
    @db_retry()
    async def create_product(
        conn: asyncpg.Connection,
        name_es: str,
        name_en: str,
        user_email: str
    ) -> Dict[str, Any]:
        if not DB.is_admin(user_email):
            raise PermissionError("Only admin users can create products")
        
        async with transaction(conn):
            existing = await conn.fetchval(
                "SELECT 1 FROM fastapi.products WHERE name_en = $1 OR name_es = $2",
                name_en,
                name_es
            )
            
            if existing:
                raise ValueError("Product with this name already exists")
            
            insert_query = """
                INSERT INTO fastapi.products (name_es, name_en)
                VALUES ($1, $2)
                RETURNING uuid, name_es, name_en, created_at
            """
            
            row = await conn.fetchrow(insert_query, name_es, name_en)
            logger.info("product_created", product_uuid=str(row["uuid"]))
            return dict(row)

    @staticmethod
    @db_retry()
    async def update_product_by_uuid(
        conn: asyncpg.Connection,
        product_uuid: UUID,
        name_es: Optional[str],
        name_en: Optional[str],
        user_email: str
    ) -> Dict[str, Any]:
        if not DB.is_admin(user_email):
            raise PermissionError("Only admin users can update products")
        
        async with transaction(conn):
            existing = await conn.fetchval(
                "SELECT 1 FROM fastapi.products WHERE uuid = $1",
                product_uuid
            )
            
            if not existing:
                raise ValueError(f"Product with UUID {product_uuid} not found")
            
            update_fields = []
            params = []
            param_count = 1
            
            if name_es is not None:
                update_fields.append(f"name_es = ${param_count}")
                params.append(name_es)
                param_count += 1
            
            if name_en is not None:
                update_fields.append(f"name_en = ${param_count}")
                params.append(name_en)
                param_count += 1
            
            if not update_fields:
                raise ValueError("No fields provided for update")
            
            params.append(product_uuid)
            
            update_query = f"""
                UPDATE fastapi.products
                SET {', '.join(update_fields)}
                WHERE uuid = ${param_count}
                RETURNING uuid, name_es, name_en, created_at
            """
            
            row = await conn.fetchrow(update_query, *params)
            logger.info("product_updated", product_uuid=str(product_uuid))
            return dict(row)

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

    # ============================================================================
    # COMMUNE OPERATIONS
    # ============================================================================
    
    @staticmethod
    @db_retry()
    async def get_all_communes(
        conn: asyncpg.Connection,
        limit: int = 500,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT uuid, name, created_at
            FROM fastapi.communes
            ORDER BY name ASC
            LIMIT $1 OFFSET $2
        """
        rows = await conn.fetch(query, limit, offset)
        return [dict(row) for row in rows]

    @staticmethod
    @db_retry()
    async def get_commune_by_uuid(
        conn: asyncpg.Connection,
        commune_uuid: UUID
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT uuid, name, created_at
            FROM fastapi.communes
            WHERE uuid = $1
        """
        row = await conn.fetchrow(query, commune_uuid)
        return dict(row) if row else None

    @staticmethod
    @db_retry()
    async def create_commune(
        conn: asyncpg.Connection,
        name: str,
        user_email: str
    ) -> Dict[str, Any]:
        if not DB.is_admin(user_email):
            raise PermissionError("Only admin users can create communes")
        
        async with transaction(conn):
            existing = await conn.fetchval(
                "SELECT 1 FROM fastapi.communes WHERE name = $1",
                name
            )
            
            if existing:
                raise ValueError("Commune with this name already exists")
            
            insert_query = """
                INSERT INTO fastapi.communes (name)
                VALUES ($1)
                RETURNING uuid, name, created_at
            """
            
            row = await conn.fetchrow(insert_query, name)
            logger.info("commune_created", commune_uuid=str(row["uuid"]))
            return dict(row)

    @staticmethod
    @db_retry()
    async def update_commune_by_uuid(
        conn: asyncpg.Connection,
        commune_uuid: UUID,
        name: Optional[str],
        user_email: str
    ) -> Dict[str, Any]:
        if not DB.is_admin(user_email):
            raise PermissionError("Only admin users can update communes")
        
        async with transaction(conn):
            existing = await conn.fetchval(
                "SELECT 1 FROM fastapi.communes WHERE uuid = $1",
                commune_uuid
            )
            
            if not existing:
                raise ValueError(f"Commune with UUID {commune_uuid} not found")
            
            if name is None:
                raise ValueError("Name is required for update")
            
            update_query = """
                UPDATE fastapi.communes
                SET name = $1
                WHERE uuid = $2
                RETURNING uuid, name, created_at
            """
            
            row = await conn.fetchrow(update_query, name, commune_uuid)
            logger.info("commune_updated", commune_uuid=str(commune_uuid))
            return dict(row)

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

    # ============================================================================
    # COMPANY OPERATIONS
    # ============================================================================
    
    @staticmethod
    @db_retry()
    async def get_company_by_uuid(
        conn: asyncpg.Connection,
        company_uuid: UUID
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT 
                c.uuid,
                c.user_uuid,
                c.product_uuid,
                c.commune_uuid,
                c.name,
                c.description_es,
                c.description_en,
                c.address,
                c.phone,
                c.email,
                c.image_url,
                c.created_at,
                c.updated_at,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            WHERE c.uuid = $1
        """
        row = await conn.fetchrow(query, company_uuid)
        return dict(row) if row else None

    @staticmethod
    @db_retry()
    async def get_all_companies(
        conn: asyncpg.Connection,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                c.uuid,
                c.user_uuid,
                c.product_uuid,
                c.commune_uuid,
                c.name,
                c.description_es,
                c.description_en,
                c.address,
                c.phone,
                c.email,
                c.image_url,
                c.created_at,
                c.updated_at,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            ORDER BY c.created_at DESC
            LIMIT $1 OFFSET $2
        """
        rows = await conn.fetch(query, limit, offset)
        return [dict(row) for row in rows]

    @staticmethod
    @db_retry()
    async def get_companies_by_user_uuid(
        conn: asyncpg.Connection,
        user_uuid: UUID
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                c.uuid,
                c.user_uuid,
                c.product_uuid,
                c.commune_uuid,
                c.name,
                c.description_es,
                c.description_en,
                c.address,
                c.phone,
                c.email,
                c.image_url,
                c.created_at,
                c.updated_at,
                u.name as user_name,
                u.email as user_email,
                p.name_es as product_name_es,
                p.name_en as product_name_en,
                cm.name as commune_name
            FROM fastapi.companies c
            LEFT JOIN fastapi.users u ON u.uuid = c.user_uuid
            LEFT JOIN fastapi.products p ON p.uuid = c.product_uuid
            LEFT JOIN fastapi.communes cm ON cm.uuid = c.commune_uuid
            WHERE c.user_uuid = $1
            ORDER BY c.created_at DESC
        """
        rows = await conn.fetch(query, user_uuid)
        return [dict(row) for row in rows]

    @staticmethod
    @db_retry()
    async def create_company(
        conn: asyncpg.Connection,
        user_uuid: UUID,
        product_uuid: UUID,
        commune_uuid: UUID,
        name: str,
        description_es: Optional[str],
        description_en: Optional[str],
        address: Optional[str],
        phone: Optional[str],
        email: Optional[str],
        image_url: Optional[str]
    ) -> Dict[str, Any]:
        async with transaction(conn):
            # Check if user already has a company
            existing_company = await conn.fetchval(
                "SELECT 1 FROM fastapi.companies WHERE user_uuid = $1",
                user_uuid
            )
            if existing_company:
                raise ValueError(
                    "You already have a company. Each user can only create one company. "
                    "Please update your existing company instead."
                )
            
            # Verify product exists
            product_exists = await conn.fetchval(
                "SELECT 1 FROM fastapi.products WHERE uuid = $1",
                product_uuid
            )
            if not product_exists:
                raise ValueError(f"Product with UUID {product_uuid} does not exist")
            
            # Verify commune exists
            commune_exists = await conn.fetchval(
                "SELECT 1 FROM fastapi.communes WHERE uuid = $1",
                commune_uuid
            )
            if not commune_exists:
                raise ValueError(f"Commune with UUID {commune_uuid} does not exist")
            
            insert_query = """
                INSERT INTO fastapi.companies 
                    (user_uuid, product_uuid, commune_uuid, name, description_es, 
                    description_en, address, phone, email, image_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING uuid
            """
            
            row = await conn.fetchrow(
                insert_query,
                user_uuid,
                product_uuid,
                commune_uuid,
                name,
                description_es,
                description_en,
                address,
                phone,
                email,
                image_url
            )
            
            logger.info("company_created", company_uuid=str(row["uuid"]), user_uuid=str(user_uuid))
            
            # Return complete company data
            return await DB.get_company_by_uuid(conn, row["uuid"])
    @staticmethod
    @db_retry()
    async def update_company_by_uuid(
        conn: asyncpg.Connection,
        company_uuid: UUID,
        user_uuid: UUID,
        name: Optional[str] = None,
        description_es: Optional[str] = None,
        description_en: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        image_url: Optional[str] = None,
        product_uuid: Optional[UUID] = None,
        commune_uuid: Optional[UUID] = None
    ) -> Dict[str, Any]:
        async with transaction(conn):
            # Verify ownership
            owner_check = await conn.fetchval(
                "SELECT user_uuid FROM fastapi.companies WHERE uuid = $1",
                company_uuid
            )
            
            if not owner_check:
                raise ValueError(f"Company with UUID {company_uuid} not found")
            
            if owner_check != user_uuid:
                raise PermissionError("You can only update your own companies")
            
            update_fields = []
            params = []
            param_count = 1
            
            if name is not None:
                update_fields.append(f"name = ${param_count}")
                params.append(name)
                param_count += 1
            
            if description_es is not None:
                update_fields.append(f"description_es = ${param_count}")
                params.append(description_es)
                param_count += 1
            
            if description_en is not None:
                update_fields.append(f"description_en = ${param_count}")
                params.append(description_en)
                param_count += 1
            
            if address is not None:
                update_fields.append(f"address = ${param_count}")
                params.append(address)
                param_count += 1
            
            if phone is not None:
                update_fields.append(f"phone = ${param_count}")
                params.append(phone)
                param_count += 1
            
            if email is not None:
                update_fields.append(f"email = ${param_count}")
                params.append(email)
                param_count += 1
            
            if image_url is not None:
                update_fields.append(f"image_url = ${param_count}")
                params.append(image_url)
                param_count += 1
            
            if product_uuid is not None:
                product_exists = await conn.fetchval(
                    "SELECT 1 FROM fastapi.products WHERE uuid = $1",
                    product_uuid
                )
                if not product_exists:
                    raise ValueError(f"Product with UUID {product_uuid} does not exist")
                update_fields.append(f"product_uuid = ${param_count}")
                params.append(product_uuid)
                param_count += 1
            
            if commune_uuid is not None:
                commune_exists = await conn.fetchval(
                    "SELECT 1 FROM fastapi.communes WHERE uuid = $1",
                    commune_uuid
                )
                if not commune_exists:
                    raise ValueError(f"Commune with UUID {commune_uuid} does not exist")
                update_fields.append(f"commune_uuid = ${param_count}")
                params.append(commune_uuid)
                param_count += 1
            
            if not update_fields:
                raise ValueError("No fields provided for update")
            
            update_fields.append(f"updated_at = NOW()")
            params.append(company_uuid)
            
            update_query = f"""
                UPDATE fastapi.companies
                SET {', '.join(update_fields)}
                WHERE uuid = ${param_count}
                RETURNING uuid
            """
            
            await conn.execute(update_query, *params)
            
            logger.info("company_updated", company_uuid=str(company_uuid), user_uuid=str(user_uuid))
            
            # Return complete updated company data
            return await DB.get_company_by_uuid(conn, company_uuid)

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
    @db_retry()
    async def search_companies(
        conn: asyncpg.Connection,
        query: str,
        lang: str = "es",
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search companies using materialized view with full-text search.
        
        Args:
            conn: Database connection
            query: Search query string
            lang: Language for search ('es' or 'en')
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of company dictionaries with search results
        """
        search_query = """
            SELECT 
                company_id,
                company_name,
                company_description_es,
                company_description_en,
                address,
                company_email,
                product_name_es,
                product_name_en,
                user_name,
                user_email,
                commune_name,
                ts_rank(search_vector, tsquery) AS rank
            FROM fastapi.company_search,
                 to_tsquery($1, $2) tsquery
            WHERE search_vector @@ tsquery
            ORDER BY rank DESC
            LIMIT $3 OFFSET $4
        """
        
        # Determine language config for to_tsquery
        lang_config = 'spanish' if lang == 'es' else 'english'
        
        # Format search terms for tsquery (replace spaces with & for AND search)
        formatted_query = ' & '.join(query.split())
        
        rows = await conn.fetch(
            search_query,
            lang_config,
            formatted_query,
            limit,
            offset
        )
        
        results = []
        for row in rows:
            results.append({
                "uuid": row["company_id"],
                "name": row["company_name"],
                "description": row[f"company_description_{lang}"],
                "address": row["address"],
                "email": row["company_email"],
                "product_name": row[f"product_name_{lang}"],
                "commune_name": row["commune_name"],
                "relevance_score": float(row["rank"])
            })
        
        return results

    @staticmethod
    @db_retry()
    async def admin_delete_company_by_uuid(
        conn: asyncpg.Connection,
        company_uuid: UUID,
        admin_email: str
    ) -> Dict[str, Any]:
        """
        Admin can delete any company regardless of ownership.
        
        Args:
            conn: Database connection
            company_uuid: UUID of company to delete
            admin_email: Email of admin performing the deletion
            
        Returns:
            Dictionary with deleted company info
            
        Raises:
            PermissionError: If user is not admin
            ValueError: If company not found
        """
        if not DB.is_admin(admin_email):
            raise PermissionError(
                "Only admin users can delete any company. "
                "Contact acos2014600836@gmail.com for assistance."
            )
        
        async with transaction(conn):
            company_query = """
                SELECT uuid, user_uuid, product_uuid, commune_uuid, name,
                       description_es, description_en, address, phone, email,
                       image_url, created_at, updated_at
                FROM fastapi.companies
                WHERE uuid = $1
            """
            company = await conn.fetchrow(company_query, company_uuid)
            
            if not company:
                raise ValueError(f"Company with UUID {company_uuid} not found")
            
            # Move to deleted table
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
            
            # Delete from main table
            await conn.execute("DELETE FROM fastapi.companies WHERE uuid = $1", company_uuid)
            
            logger.info(
                "admin_deleted_company",
                company_uuid=str(company_uuid),
                admin_email=admin_email
            )
            
            return {
                "uuid": str(company["uuid"]),
                "name": company["name"]
            }
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    @staticmethod
    def is_admin(email: str) -> bool:
        return email.lower() == settings.admin_email.lower()