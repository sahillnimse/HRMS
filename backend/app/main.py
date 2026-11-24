"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1.api import api_router
from app.db.session import direct_engine
from app.db.base import Base
from app.models import candidate as _candidate_models  # noqa: F401


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="AI-powered HRMS: upload resumes, parse with Gemini, manage candidates.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_router, prefix="/api/v1")

    # Ensure upload directory exists before mounting static files
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    # Serve uploaded files (dev only — production uses object storage URLs)
    app.mount("/files", StaticFiles(directory=settings.UPLOAD_DIR), name="files")

    @app.on_event("startup")
    async def on_startup():
        """Create database tables if they don't exist using the direct (unpooled) connection."""
        async with direct_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @app.get("/health")
    async def health():
        return {"status": "ok", "env": settings.APP_ENV}

    return app


app = create_app()
