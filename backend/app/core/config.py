"""
Application configuration loaded from environment variables.

Uses pydantic-settings for type-safe, validated settings with sensible
development defaults. Production values must be supplied via .env.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


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

    # --- Google Gemini ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # --- File storage (local dev) ---
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: str = ".pdf,.docx"

    # --- Security ---
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

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
