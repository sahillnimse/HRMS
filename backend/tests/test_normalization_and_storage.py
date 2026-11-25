"""Unit tests for contact normalization, storage backends and production SECRET_KEY checks."""

from io import BytesIO

import pytest
from botocore.exceptions import ClientError

from app.core.config import DEFAULT_SECRET_KEY, Settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.services.file_storage import LocalStorage, S3Storage, create_storage
from app.services.normalization import normalize_email, normalize_phone


def test_normalize_email():
    assert normalize_email("  Alice.Smith@Example.COM ") == "alice.smith@example.com"
    assert normalize_email("   ") is None
    assert normalize_email(None) is None


def test_normalize_phone_variants():
    assert normalize_phone("+91 99233-95808") == "9923395808"
    assert normalize_phone("0091 99233 95808") == "9923395808"
    assert normalize_phone("09923395808") == "9923395808"
    assert normalize_phone("9923395808") == "9923395808"
    assert normalize_phone("(555) 123-4567") == "5551234567"
    assert normalize_phone("123") is None
    assert normalize_phone(None) is None


def test_password_hash_and_jwt_roundtrip():
    hashed = hash_password("S3cret-pass!")
    assert hashed != "S3cret-pass!"
    assert verify_password("S3cret-pass!", hashed) is True
    assert verify_password("wrong", hashed) is False
    assert verify_password("x", "not-a-hash") is False

    token = create_access_token({"sub": "abc", "role": "viewer"})
    payload = decode_access_token(token)
    assert payload is not None and payload["sub"] == "abc"
    assert decode_access_token(token + "tampered") is None
    assert decode_access_token(create_access_token({"sub": "abc"}, expires_delta=-1)) is None


async def test_local_storage_roundtrip_and_traversal_guard(tmp_path):
    store = LocalStorage(upload_dir=str(tmp_path))
    meta = await store.save_file(b"%PDF-1.4 test bytes", "resume.pdf", "application/pdf")
    assert meta["file_size"] == len(b"%PDF-1.4 test bytes")
    assert await store.read_file(meta["stored_filename"]) == b"%PDF-1.4 test bytes"

    with pytest.raises(FileNotFoundError):
        await store.read_file("../../etc/passwd")

    assert await store.delete_file(meta["stored_filename"]) is True
    assert await store.delete_file(meta["stored_filename"]) is False


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket: str, Key: str):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket: str, Key: str):
        self.objects.pop((Bucket, Key), None)

    def generate_presigned_url(self, ClientMethod: str, Params: dict, ExpiresIn: int):
        return f"https://r2.example/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


async def test_s3_storage_roundtrip_with_mock_client():
    fake = _FakeS3Client()
    store = S3Storage(bucket="hrms-bucket", prefix="resumes", client=fake)

    meta = await store.save_file(b"hello-r2", "cv.pdf", "application/pdf")
    assert meta["file_path"].startswith("s3://hrms-bucket/resumes/")
    assert await store.read_file(meta["stored_filename"]) == b"hello-r2"
    assert "hrms-bucket/resumes/" in await store.get_url(meta["stored_filename"])

    assert await store.delete_file(meta["stored_filename"]) is True
    with pytest.raises(FileNotFoundError):
        await store.read_file(meta["stored_filename"])


def test_create_storage_selection():
    assert isinstance(create_storage("local"), LocalStorage)
    with pytest.raises(ValueError):
        create_storage("unknown-backend")


def test_production_secret_key_validation():
    with pytest.raises(RuntimeError):
        Settings(APP_ENV="production", SECRET_KEY=DEFAULT_SECRET_KEY).validate_production_security()
    with pytest.raises(RuntimeError):
        Settings(APP_ENV="production", SECRET_KEY="too-short").validate_production_security()

    Settings(APP_ENV="production", SECRET_KEY="a" * 40).validate_production_security()
    Settings(APP_ENV="development", SECRET_KEY=DEFAULT_SECRET_KEY).validate_production_security()
