"""
File storage abstraction layer.

LocalStorage is the development implementation. To swap to Supabase Storage
or Cloudflare R2 in production, subclass BaseStorage and implement the same
interface — no changes needed in routes or CRUD.
"""

import os
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.core.config import settings


class BaseStorage(ABC):
    @abstractmethod
    async def save_file(self, file_bytes: bytes, original_filename: str, content_type: str) -> dict:
        """Save bytes and return metadata dict."""
        ...

    @abstractmethod
    async def get_file_path(self, stored_filename: str) -> str:
        """Return filesystem path or public URL for a stored file."""
        ...

    @abstractmethod
    async def get_url(self, stored_filename: str) -> str:
        """Return a downloadable/viewable URL for the file."""
        ...

    @abstractmethod
    async def delete_file(self, stored_filename: str) -> bool:
        ...


class LocalStorage(BaseStorage):
    """Development storage: writes files to UPLOAD_DIR on disk."""

    def __init__(self, upload_dir: str | None = None):
        self.upload_dir = Path(upload_dir or settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _stored_name(self, original_filename: str) -> str:
        ext = Path(original_filename).suffix
        return f"{uuid.uuid4().hex}{ext}"

    async def save_file(self, file_bytes: bytes, original_filename: str, content_type: str) -> dict:
        stored_name = self._stored_name(original_filename)
        file_path = self.upload_dir / stored_name
        file_path.write_bytes(file_bytes)
        return {
            "stored_filename": stored_name,
            "original_filename": original_filename,
            "file_path": str(file_path),
            "file_size": len(file_bytes),
            "content_type": content_type,
        }

    async def get_file_path(self, stored_filename: str) -> str:
        return str(self.upload_dir / stored_filename)

    async def get_url(self, stored_filename: str) -> str:
        # For local dev, serve via a static route or return the path
        return f"/files/{stored_filename}"

    async def delete_file(self, stored_filename: str) -> bool:
        path = self.upload_dir / stored_filename
        if path.exists():
            path.unlink()
            return True
        return False


# Singleton instance for the app
storage = LocalStorage()
