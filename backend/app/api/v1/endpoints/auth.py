"""Authentication, refresh token rotation/revocation, and admin user management endpoints."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import create_access_token
from app.crud.user import (
    authenticate_user,
    create_user,
    get_refresh_token,
    get_user_by_email,
    get_user_by_id,
    issue_refresh_token,
    list_users,
    revoke_all_user_refresh_tokens,
    revoke_refresh_token,
)
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserResponse

router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        max_age=max_age,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path="/api/v1/auth",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email + password, enforce rate limiting & lockout, issue a
    short-lived JWT access token, and set an httpOnly refresh cookie.
    """
    ip = _client_ip(request)
    email = str(payload.email)

    retry_after = login_rate_limiter.check_blocked(ip, email)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = await authenticate_user(db, email, payload.password)
    if not user:
        lock_secs = login_rate_limiter.record_failure(ip, email)
        if lock_secs is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Account temporarily locked.",
                headers={"Retry-After": str(lock_secs)},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_rate_limiter.record_success(ip, email)

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    raw_refresh = await issue_refresh_token(
        db,
        user_id=user.id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate the httpOnly refresh cookie and return a fresh short-lived access token.
    Replaying a revoked refresh token revokes all active sessions for that user.
    """
    raw_refresh = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    record = await get_refresh_token(db, raw_refresh)
    if not record:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Reuse detection: if an already-revoked token is presented, revoke all user sessions
    if record.revoked_at is not None:
        await revoke_all_user_refresh_tokens(db, record.user_id)
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. Please sign in again.",
        )

    if record.expires_at <= datetime.now(timezone.utc):
        await revoke_refresh_token(db, record)
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = await get_user_by_id(db, record.user_id)
    if not user or not user.is_active:
        await revoke_refresh_token(db, record)
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Rotate refresh token
    await revoke_refresh_token(db, record)
    new_refresh = await issue_refresh_token(
        db,
        user_id=user.id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, new_refresh)

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current refresh token (if present) and clear the refresh cookie."""
    raw_refresh = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw_refresh:
        record = await get_refresh_token(db, raw_refresh)
        if record and record.revoked_at is None:
            await revoke_refresh_token(db, record)
    _clear_refresh_cookie(response)
    return None


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke every active refresh session for the authenticated user."""
    await revoke_all_user_refresh_tokens(db, current_user.id)
    _clear_refresh_cookie(response)
    return None


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_endpoint(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    """Admin-only: create a new user account."""
    existing = await get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )
    return await create_user(
        db,
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active,
    )


@router.get("/users", response_model=List[UserResponse])
async def list_users_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    """Admin-only: list all users."""
    return await list_users(db)
