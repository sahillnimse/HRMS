"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.crud.user import create_user, get_user_by_email
from app.db.session import AsyncSessionLocal, direct_engine, engine
from app.models.user import UserRole
from app.services.cleanup import orphan_cleanup_loop

logger = logging.getLogger(__name__)


async def _bootstrap_admin_if_configured() -> None:
    """Optionally create an initial admin user from env vars if not already present."""
    email = (settings.BOOTSTRAP_ADMIN_EMAIL or "").strip()
    password = settings.BOOTSTRAP_ADMIN_PASSWORD or ""
    if not email or not password:
        return
    async with AsyncSessionLocal() as db:
        existing = await get_user_by_email(db, email)
        if not existing:
            await create_user(
                db,
                email=email,
                password=password,
                full_name=settings.BOOTSTRAP_ADMIN_NAME,
                role=UserRole.admin,
            )
            logger.info("Bootstrapped initial admin user: %s", email)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Validate production security, optionally seed bootstrap admin, and run orphan cleanup."""
    settings.validate_production_security()

    try:
        await _bootstrap_admin_if_configured()
    except Exception:
        logger.warning("Skipping bootstrap admin check (migrations may not have run yet).", exc_info=True)

    cleanup_task: asyncio.Task | None = None
    if settings.ENABLE_CLEANUP_SCHEDULER:
        cleanup_task = asyncio.create_task(orphan_cleanup_loop(AsyncSessionLocal))

    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
        await engine.dispose()
        if direct_engine is not engine:
            await direct_engine.dispose()


def _init_optional_sentry() -> None:
    """Optionally initialize Sentry error monitoring with strict zero-PII defaults."""
    dsn = (settings.SENTRY_DSN or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk  # type: ignore[import-not-found]

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.APP_ENV,
            traces_sample_rate=float(settings.SENTRY_TRACES_SAMPLE_RATE),
            send_default_pii=False,
        )
        logger.info("Sentry monitoring initialized (send_default_pii=False).")
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; skipping Sentry init.")


def create_app() -> FastAPI:
    _init_optional_sentry()
    is_prod = settings.APP_ENV.lower() == "production"
    app = FastAPI(
        title=settings.APP_NAME,
        description="AI-powered HRMS: upload resumes, parse with AI, manage candidates.",
        version="0.6.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok", "env": settings.APP_ENV}

    return app


app = create_app()
