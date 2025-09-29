import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Add the parent directory to the path so we can import our app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import your settings and models with error handling
try:
    from app.config import settings
    from app.models import Base
except ImportError as e:
    raise ImportError(f"Could not import app modules. Make sure your app is in the Python path: {e}")

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for 'autogenerate' support
target_metadata = Base.metadata

def get_database_url():
    """Get database URL with proper SSL configuration"""
    base_url = settings.alembic_database_url

    if hasattr(settings, 'db_ssl_mode') and settings.db_ssl_mode != "disable":
        separator = "&" if "?" in base_url else "?"
        base_url += f"{separator}sslmode={settings.db_ssl_mode}"
    
    return base_url

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Create configuration dict
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()
    
    # Build connect_args
    connect_args = {}
    # psycopg2 does not support command_timeout / server_timeout
    # If you need statement timeout, use:
    connect_args["options"] = "-c statement_timeout=60000"
    # Add schema search path for PostgreSQL
    # Add schema search path for PostgreSQL
    connect_args["options"] = "-c search_path=public"

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()