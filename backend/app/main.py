"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.crud.user import create_user, get_user_by_email
from app.db.session import AsyncSessionLocal
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


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="AI-powered HRMS: upload resumes, parse with AI, manage candidates.",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
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
