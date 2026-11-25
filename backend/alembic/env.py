"""Alembic migration environment (uses direct/unpooled Neon Postgres URL)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401  -- ensure all models are registered on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_sync_migration_url() -> str:
    """
    Prefer DATABASE_URL_UNPOOLED (Neon direct connection, required for DDL/migrations),
    falling back to DATABASE_URL_SYNC or DATABASE_URL, normalized to psycopg2.
    """
    raw = settings.DATABASE_URL_UNPOOLED or settings.DATABASE_URL_SYNC or settings.DATABASE_URL
    url = raw.strip()
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgresql+asyncpg://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    return url


def run_migrations_offline() -> None:
    url = _get_sync_migration_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _get_sync_migration_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
