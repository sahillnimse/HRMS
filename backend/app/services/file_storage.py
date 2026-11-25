"""
File storage abstraction layer.

`BaseStorage` defines the storage contract.
- `LocalStorage` writes to `UPLOAD_DIR` (development default).
- `S3Storage` targets S3-compatible object storage such as Cloudflare R2
  when `STORAGE_BACKEND` is set to `"s3"` or `"r2"`.

All resume downloads are streamed through authenticated API routes rather than
a public static mount.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class BaseStorage(ABC):
    @abstractmethod
    async def save_file(
        self,
        file_bytes: bytes,
        original_filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        """Save bytes and return metadata dict."""
        ...

    @abstractmethod
    async def get_file_path(self, stored_filename: str) -> str:
        """Return filesystem path or object key for a stored file."""
        ...

    @abstractmethod
    async def get_url(self, stored_filename: str) -> str:
        """Return an identifier or URL for the stored file."""
        ...

    @abstractmethod
    async def read_file(self, stored_filename: str) -> bytes:
        """Read full bytes of a stored file for authenticated streaming."""
        ...

    @abstractmethod
    async def delete_file(self, stored_filename: str) -> bool:
        """Delete a stored file. Returns True if removed, False if missing."""
        ...


class LocalStorage(BaseStorage):
    """Development storage: writes files to UPLOAD_DIR on disk."""

    def __init__(self, upload_dir: str | None = None):
        self.upload_dir = Path(upload_dir or settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _stored_name(self, original_filename: str) -> str:
        ext = Path(original_filename).suffix.lower()
        return f"{uuid.uuid4().hex}{ext}"

    def _safe_path(self, stored_filename: str) -> Path:
        # Prevent path traversal by forcing basename resolution under upload_dir
        name = Path(stored_filename).name
        return self.upload_dir / name

    async def save_file(
        self,
        file_bytes: bytes,
        original_filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        stored_name = self._stored_name(original_filename)
        file_path = self._safe_path(stored_name)
        await asyncio.to_thread(file_path.write_bytes, file_bytes)
        return {
            "stored_filename": stored_name,
            "original_filename": original_filename,
            "file_path": str(file_path),
            "file_size": len(file_bytes),
            "content_type": content_type,
        }

    async def get_file_path(self, stored_filename: str) -> str:
        return str(self._safe_path(stored_filename))

    async def get_url(self, stored_filename: str) -> str:
        return f"local://{Path(stored_filename).name}"

    async def read_file(self, stored_filename: str) -> bytes:
        path = self._safe_path(stored_filename)
        if not path.exists():
            raise FileNotFoundError(f"Stored file not found: {stored_filename}")
        return await asyncio.to_thread(path.read_bytes)

    async def delete_file(self, stored_filename: str) -> bool:
        path = self._safe_path(stored_filename)
        if path.exists():
            await asyncio.to_thread(path.unlink)
            return True
        return False


class S3Storage(BaseStorage):
    """
    S3-compatible object storage implementation (works with Cloudflare R2,
    AWS S3, MinIO, etc.).
    """

    def __init__(
        self,
        *,
        bucket: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        prefix: Optional[str] = None,
        client: Any = None,
    ):
        self.bucket = bucket or settings.S3_BUCKET
        if not self.bucket:
            raise ValueError("S3_BUCKET must be configured when STORAGE_BACKEND is s3/r2")
        self.prefix = (prefix if prefix is not None else settings.S3_PREFIX).strip("/")
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url or settings.S3_ENDPOINT_URL,
            region_name=region_name or settings.S3_REGION or "auto",
            aws_access_key_id=access_key_id or settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=secret_access_key or settings.S3_SECRET_ACCESS_KEY,
        )

    def _stored_name(self, original_filename: str) -> str:
        ext = Path(original_filename).suffix.lower()
        return f"{uuid.uuid4().hex}{ext}"

    def _object_key(self, stored_filename: str) -> str:
        name = Path(stored_filename).name
        return f"{self.prefix}/{name}" if self.prefix else name

    async def save_file(
        self,
        file_bytes: bytes,
        original_filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        stored_name = self._stored_name(original_filename)
        key = self._object_key(stored_name)

        def _put() -> None:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )

        await asyncio.to_thread(_put)
        return {
            "stored_filename": stored_name,
            "original_filename": original_filename,
            "file_path": f"s3://{self.bucket}/{key}",
            "file_size": len(file_bytes),
            "content_type": content_type,
        }

    async def get_file_path(self, stored_filename: str) -> str:
        return f"s3://{self.bucket}/{self._object_key(stored_filename)}"

    async def get_url(self, stored_filename: str) -> str:
        key = self._object_key(stored_filename)

        def _presign() -> str:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=300,
            )

        return await asyncio.to_thread(_presign)

    async def read_file(self, stored_filename: str) -> bytes:
        key = self._object_key(stored_filename)

        def _get() -> bytes:
            try:
                obj = self.client.get_object(Bucket=self.bucket, Key=key)
                return obj["Body"].read()
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"NoSuchKey", "404", "NotFound"}:
                    raise FileNotFoundError(f"Stored file not found in S3: {stored_filename}") from exc
                raise

        return await asyncio.to_thread(_get)

    async def delete_file(self, stored_filename: str) -> bool:
        key = self._object_key(stored_filename)

        def _delete() -> bool:
            try:
                self.client.delete_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return False

        return await asyncio.to_thread(_delete)


def create_storage(backend: Optional[str] = None) -> BaseStorage:
    """Instantiate the configured storage backend."""
    selected = (backend or settings.STORAGE_BACKEND or "local").strip().lower()
    if selected in {"s3", "r2"}:
        return S3Storage()
    if selected == "local":
        return LocalStorage()
    raise ValueError(f"Unsupported STORAGE_BACKEND: {selected!r} (use 'local', 's3', or 'r2')")


# Active storage instance for the application
storage: BaseStorage = create_storage()
