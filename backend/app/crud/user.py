"""Async CRUD operations for User accounts."""

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
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
