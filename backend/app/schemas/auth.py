"""Pydantic v2 schemas for authentication and user management."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(default="", max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.recruiter
    is_active: bool = True


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
