"""Async CRUD operations for User accounts and server-side refresh tokens."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User, UserRole
from app.services.normalization import normalize_email


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    norm = normalize_email(email)
    if not norm:
        return None
    result = await db.execute(select(User).where(User.email == norm))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID | str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession) -> Sequence[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str = "",
    role: UserRole = UserRole.recruiter,
    is_active: bool = True,
) -> User:
    norm_email = normalize_email(email)
    if not norm_email:
        raise ValueError("Email is required")
    user = User(
        email=norm_email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    user = await get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def issue_refresh_token(
    db: AsyncSession,
    *,
    user_id: UUID,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Create a persisted hashed refresh token and return the raw cookie value."""
    raw = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        expires_at=expires_at,
        ip_address=(ip_address or "")[:64] or None,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(record)
    await db.commit()
    return raw


async def get_refresh_token(db: AsyncSession, raw_token: str) -> Optional[RefreshToken]:
    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, record: RefreshToken) -> None:
    record.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def revoke_all_user_refresh_tokens(db: AsyncSession, user_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()
