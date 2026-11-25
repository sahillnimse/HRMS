"""
Application configuration loaded from environment variables.

Uses pydantic-settings for type-safe, validated settings with sensible
development defaults. Production values must be supplied via environment
variables or .env.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent

DEFAULT_SECRET_KEY = "change-me-in-production"


class Settings(BaseSettings):
    # --- Application ---
    APP_NAME: str = "HRMS AI"
    APP_ENV: str = "development"
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"

    # --- Database (PostgreSQL / Neon Lakebase Postgres + asyncpg) ---
    DATABASE_URL: str = "postgresql+asyncpg://hrms_user:hrms_pass@localhost:5432/hrms_db"
    DATABASE_URL_UNPOOLED: Optional[str] = None
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://hrms_user:hrms_pass@localhost:5432/hrms_db"

    # --- Google Gemini / OpenRouter ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # --- Semantic Search & Embeddings (Phase 2) ---
    ENABLE_SEMANTIC_SEARCH: bool = True
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSIONS: int = 768

    # --- File Storage ---
    STORAGE_BACKEND: str = "local"  # "local" | "s3" | "r2"
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: str = ".pdf,.docx"

    # --- S3 / Cloudflare R2 (used when STORAGE_BACKEND is "s3" or "r2") ---
    S3_ENDPOINT_URL: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_REGION: str = "auto"
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_PREFIX: str = "resumes"

    # --- Orphan Resume Cleanup ---
    ORPHAN_MAX_AGE_HOURS: int = 24
    ORPHAN_CLEANUP_INTERVAL_MINUTES: int = 60
    ENABLE_CLEANUP_SCHEDULER: bool = True

    # --- Duplicate Detection ---
    DUPLICATE_NAME_SIMILARITY_THRESHOLD: float = 0.6

    # --- Security & Auth ---
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "hrms_refresh_token"
    REFRESH_COOKIE_SECURE: Optional[bool] = None
    REFRESH_COOKIE_SAMESITE: str = "lax"
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_MINUTES: int = 15
    LOGIN_LOCKOUT_MINUTES: int = 15
    BOOTSTRAP_ADMIN_EMAIL: Optional[str] = None
    BOOTSTRAP_ADMIN_PASSWORD: Optional[str] = None
    BOOTSTRAP_ADMIN_NAME: str = "System Admin"

    @property
    def cookie_secure(self) -> bool:
        if self.REFRESH_COOKIE_SECURE is not None:
            return self.REFRESH_COOKIE_SECURE
        return self.APP_ENV.lower() == "production"

    # CORS origins (accepts JSON array or comma-separated string)
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    def validate_production_security(self) -> None:
        """Fail fast on startup in production if SECRET_KEY is unsafe."""
        if self.APP_ENV.lower() == "production":
            key = (self.SECRET_KEY or "").strip()
            if not key or key == DEFAULT_SECRET_KEY or len(key) < 32:
                raise RuntimeError(
                    "Refusing to start in production with default or weak SECRET_KEY "
                    "(must be a unique random string of at least 32 characters)."
                )

    model_config = {
        "env_file": (str(_BACKEND_DIR / ".env"), str(_REPO_ROOT / ".env.local")),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
