"""Security utilities: Argon2 password hashing and PyJWT access tokens."""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

JWT_ALGORITHM = "HS256"
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: int | None = None,
) -> str:
    """Sign a JWT access token with PyJWT."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a JWT access token; returns None on any error."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload if isinstance(payload, dict) else None
    except jwt.PyJWTError:
        return None
