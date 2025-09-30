import asyncpg
import structlog
import ssl
import logging
from typing import AsyncGenerator, Optional, Dict, Any
from contextlib import asynccontextmanager
from app.config import settings

# Configure structlog BEFORE getting a logger
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # Add context variables
        structlog.processors.add_log_level,        # Add log level to output
        structlog.processors.TimeStamper(fmt="iso"),  # ISO timestamp
        structlog.processors.StackInfoRenderer(),  # Stack traces if available
        structlog.processors.format_exc_info,      # Format exceptions
        structlog.processors.JSONRenderer()        # Output as JSON
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),  # Set log level
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),  # Print to stdout
    cache_logger_on_first_use=True,
)

# NOW get the logger after configuration
logger = structlog.get_logger()

# Connection pools
write_pool: Optional[asyncpg.Pool] = None
read_pool: Optional[asyncpg.Pool] = None

class DatabasePoolManager:
    def __init__(self):
        self.write_pool: Optional[asyncpg.Pool] = None
        self.read_pool: Optional[asyncpg.Pool] = None
        self._pool_stats = {"connections": 0, "queries": 0, "errors": 0}
    
    async def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for secure database connections"""
        if settings.db_ssl_mode != "require":
            return None
        
        # For "require" mode: encrypt connection but don't verify server cert
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        return ssl_context
    
    async def init_pools(self):
        """Initialize connection pools with proper configuration"""
        global write_pool, read_pool
        
        ssl_context = await self._create_ssl_context()
        
        try:
            # Write pool (main database)
            self.write_pool = write_pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
                max_queries=settings.db_pool_max_queries,
                max_inactive_connection_lifetime=settings.db_pool_max_inactive,
                command_timeout=settings.db_command_timeout,
                server_settings={
                    'application_name': f'{settings.project_name}_write',
                    'tcp_keepalives_idle': '600',
                    'tcp_keepalives_interval': '30',
                    'tcp_keepalives_count': '3',
                },
                ssl=ssl_context,
                init=self._init_connection
            )
            
            # Read-only pool (if configured)
            if settings.db_read_only_url:
                self.read_pool = read_pool = await asyncpg.create_pool(
                    dsn=settings.db_read_only_url,
                    min_size=max(1, settings.db_pool_min_size // 2),
                    max_size=settings.db_pool_max_size,
                    max_queries=settings.db_pool_max_queries,
                    max_inactive_connection_lifetime=settings.db_pool_max_inactive,
                    command_timeout=settings.db_command_timeout,
                    server_settings={
                        'application_name': f'{settings.project_name}_read',
                        'default_transaction_read_only': 'on',
                    },
                    ssl=ssl_context,
                    init=self._init_connection
                )
            else:
                self.read_pool = read_pool = self.write_pool
            
            logger.info("database_pools_initialized", 
                       write_pool_size=self.write_pool.get_size(),
                       read_pool_size=self.read_pool.get_size())
            
        except Exception as e:
            logger.error("database_pool_init_failed", error=str(e), exc_info=True)
            raise
    
    async def _init_connection(self, conn: asyncpg.Connection):
        """Initialize each connection with custom settings"""
        # Set connection-level parameters
        await conn.execute("SET timezone TO 'UTC'")
        await conn.execute(f"SET statement_timeout TO '{settings.db_timeout}s'")
        await conn.execute("SET log_statement_stats TO off")
        
        # Enable query logging for slow queries
        if settings.debug:
            await conn.execute(f"SET log_min_duration_statement TO {int(settings.db_slow_query_threshold * 1000)}")
    
    async def close_pools(self):
        """Close all connection pools"""
        if self.write_pool:
            await self.write_pool.close()
        if self.read_pool and self.read_pool != self.write_pool:
            await self.read_pool.close()
        logger.info("database_pools_closed")
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get current pool statistics"""
        stats = {}
        if self.write_pool:
            stats["write_pool"] = {
                "size": self.write_pool.get_size(),
                "min_size": self.write_pool.get_min_size(),
                "max_size": self.write_pool.get_max_size(),
                "idle_connections": self.write_pool.get_idle_size(),
            }
        if self.read_pool and self.read_pool != self.write_pool:
            stats["read_pool"] = {
                "size": self.read_pool.get_size(),
                "min_size": self.read_pool.get_min_size(),
                "max_size": self.read_pool.get_max_size(),
                "idle_connections": self.read_pool.get_idle_size(),
            }
        return stats

# Global pool manager
pool_manager = DatabasePoolManager()

async def init_db_pools():
    await pool_manager.init_pools()

async def close_db_pools():
    await pool_manager.close_pools()

@asynccontextmanager
async def get_db_connection(read_only: bool = False) -> AsyncGenerator[asyncpg.Connection, None]:
    """Get database connection with proper error handling"""
    pool = read_pool if read_only else write_pool
    
    if not pool:
        raise RuntimeError("Database pool not initialized")
    
    async with pool.acquire() as conn:
        try:
            yield conn
        except Exception as e:
            logger.error("database_connection_error", error=str(e), exc_info=True)
            raise

# Dependency for FastAPI
async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    async with get_db_connection() as conn:
        yield conn

async def get_read_db() -> AsyncGenerator[asyncpg.Connection, None]:
    async with get_db_connection(read_only=True) as conn:
        yield conn