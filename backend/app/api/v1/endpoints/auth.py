"""Authentication and admin user management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.security import create_access_token
from app.crud.user import authenticate_user, create_user, get_user_by_email, list_users
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserResponse

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password and issue a JWT."""
    user = await authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


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
