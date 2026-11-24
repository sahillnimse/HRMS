from typing import Any, AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _normalize_asyncpg_url(raw_url: str) -> tuple[str, dict[str, Any]]:
    """
    Convert a standard Postgres/Neon connection string into an asyncpg-safe URL
    and connect_args dict.

    - Rewrites postgres:// and postgresql:// to postgresql+asyncpg://
    - Translates libpq sslmode/channel_binding query params to asyncpg connect_args
    - Disables asyncpg statement cache on Neon PgBouncer (-pooler) endpoints
    """
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    parsed = urlparse(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    connect_args: dict[str, Any] = {}

    sslmode = query_params.pop("sslmode", None)
    ssl_param = query_params.pop("ssl", None)
    query_params.pop("channel_binding", None)

    if sslmode in {"require", "verify-ca", "verify-full", "prefer"} or ssl_param == "require":
        connect_args["ssl"] = "require"
    elif parsed.hostname and parsed.hostname.endswith(".neon.tech"):
        connect_args["ssl"] = "require"

    # Neon pooled connections route through PgBouncer in transaction mode,
    # which does not support asyncpg's per-connection prepared statement cache.
    if parsed.hostname and "-pooler" in parsed.hostname:
        connect_args["statement_cache_size"] = 0

    clean_url = urlunparse(parsed._replace(query=urlencode(query_params)))
    return clean_url, connect_args


def _make_engine(raw_url: str, *, pool_size: int = 10, max_overflow: int = 20) -> AsyncEngine:
    async_url, connect_args = _normalize_asyncpg_url(raw_url)
    return create_async_engine(
        async_url,
        echo=settings.APP_ENV == "development",
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=pool_size,
        max_overflow=max_overflow,
        connect_args=connect_args,
    )


# Pooled engine for application query traffic (Neon DATABASE_URL)
engine = _make_engine(settings.DATABASE_URL)

# Direct (unpooled) engine for DDL / schema creation & migrations (Neon DATABASE_URL_UNPOOLED)
direct_engine = (
    _make_engine(settings.DATABASE_URL_UNPOOLED, pool_size=2, max_overflow=2)
    if settings.DATABASE_URL_UNPOOLED
    else engine
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
