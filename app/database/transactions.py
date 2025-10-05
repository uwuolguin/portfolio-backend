import asyncpg
import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List, Dict, Any, Callable
from enum import Enum
from uuid import UUID

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
        logger.debug(
            "transaction_started",
            isolation=isolation.value,
            readonly=readonly
        )
        yield conn
        await conn.execute("COMMIT")
        logger.debug("transaction_committed")
    except Exception as e:
        await conn.execute("ROLLBACK")
        logger.warning(
            "transaction_rolled_back",
            error=str(e),
            error_type=type(e).__name__
        )
        raise


class TransactionManager:
    @staticmethod
    async def soft_delete_record(
        conn: asyncpg.Connection,
        table: str,
        deleted_table: str,
        record_uuid: UUID,
        schema: str = "fastapi"
    ) -> bool:
        async with transaction(conn):
            select_sql = f"""
                SELECT * FROM {schema}.{table}
                WHERE uuid = $1
            """
            record = await conn.fetchrow(select_sql, record_uuid)
            if not record:
                logger.info(
                    "soft_delete_record_not_found",
                    table=table,
                    uuid=str(record_uuid)
                )
                return False
            columns = [col for col in record.keys()]
            column_names = ', '.join(columns)
            placeholders = ', '.join([f'${i+1}' for i in range(len(columns))])
            insert_sql = f"""
                INSERT INTO {schema}.{deleted_table} ({column_names})
                VALUES ({placeholders})
            """
            values = tuple(record[col] for col in columns)
            await conn.execute(insert_sql, *values)
            delete_sql = f"""
                DELETE FROM {schema}.{table}
                WHERE uuid = $1
            """
            await conn.execute(delete_sql, record_uuid)
            logger.info(
                "soft_delete_completed",
                table=table,
                uuid=str(record_uuid)
            )
            return True

    @staticmethod
    async def batch_upsert(
        conn: asyncpg.Connection,
        table: str,
        records: List[Dict[str, Any]],
        conflict_columns: List[str],
        update_columns: Optional[List[str]] = None,
        schema: str = "fastapi"
    ) -> int:
        if not records:
            return 0
        columns = list(records[0].keys())
        column_names = ', '.join(columns)
        placeholders = ', '.join([f'${i+1}' for i in range(len(columns))])
        conflict_cols = ', '.join(conflict_columns)
        if update_columns:
            update_clause = ', '.join(
                [f'{col} = EXCLUDED.{col}' for col in update_columns]
            )
            conflict_action = f"DO UPDATE SET {update_clause}"
        else:
            conflict_action = "DO NOTHING"
        upsert_sql = f"""
            INSERT INTO {schema}.{table} ({column_names})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_cols})
            {conflict_action}
        """
        processed = 0
        async with transaction(conn):
            for record in records:
                values = tuple(record[col] for col in columns)
                await conn.execute(upsert_sql, *values)
                processed += 1
        logger.info(
            "batch_upsert_completed",
            table=table,
            records_processed=processed
        )
        return processed

    @staticmethod
    async def execute_batch(
        conn: asyncpg.Connection,
        operations: List[Callable],
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED
    ) -> List[Any]:
        results = []
        async with transaction(conn, isolation=isolation):
            for operation in operations:
                result = await operation()
                results.append(result)
        logger.info(
            "batch_execution_completed",
            operations_count=len(operations)
        )
        return results

    @staticmethod
    async def refresh_materialized_view(
        conn: asyncpg.Connection,
        view_name: str,
        schema: str = "fastapi",
        concurrently: bool = False
    ) -> None:
        concurrent_keyword = "CONCURRENTLY" if concurrently else ""
        refresh_sql = f"""
            REFRESH MATERIALIZED VIEW {concurrent_keyword}
            {schema}.{view_name}
        """
        try:
            await conn.execute(refresh_sql)
            logger.info(
                "materialized_view_refreshed",
                view=f"{schema}.{view_name}",
                concurrent=concurrently
            )
        except asyncpg.PostgresError as e:
            logger.error(
                "materialized_view_refresh_failed",
                view=f"{schema}.{view_name}",
                error=str(e),
                error_code=e.sqlstate
            )
            raise

    @staticmethod
    async def atomic_update_with_validation(
        conn: asyncpg.Connection,
        table: str,
        record_uuid: UUID,
        updates: Dict[str, Any],
        validator: Optional[Callable] = None,
        schema: str = "fastapi"
    ) -> Optional[Dict[str, Any]]:
        if not updates:
            raise ValueError("No updates provided")
        async with transaction(conn):
            select_sql = f"""
                SELECT * FROM {schema}.{table}
                WHERE uuid = $1
                FOR UPDATE
            """
            current = await conn.fetchrow(select_sql, record_uuid)
            if not current:
                logger.warning(
                    "update_record_not_found",
                    table=table,
                    uuid=str(record_uuid)
                )
                return None
            if validator:
                await validator(dict(current))
            set_clauses = []
            values = []
            for idx, (field, value) in enumerate(updates.items(), start=1):
                set_clauses.append(f"{field} = ${idx}")
                values.append(value)
            values.append(record_uuid)
            update_sql = f"""
                UPDATE {schema}.{table}
                SET {', '.join(set_clauses)}, updated_at = NOW()
                WHERE uuid = ${len(values)}
                RETURNING *
            """
            updated = await conn.fetchrow(update_sql, *values)
            logger.info(
                "atomic_update_completed",
                table=table,
                uuid=str(record_uuid),
                fields_updated=list(updates.keys())
            )
            return dict(updated) if updated else None


async def with_transaction(
    conn: asyncpg.Connection,
    operation: Callable,
    isolation: IsolationLevel = IsolationLevel.READ_COMMITTED
) -> Any:
    async with transaction(conn, isolation=isolation):
        return await operation()


async def readonly_transaction(
    conn: asyncpg.Connection,
    operation: Callable
) -> Any:
    async with transaction(conn, readonly=True):
        return await operation()
