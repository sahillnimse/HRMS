"""Skill normalization management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.matching import list_skill_normalizations, upsert_skill_normalization
from app.models.user import User, UserRole
from app.schemas.matching import SkillNormalizationCreate, SkillNormalizationResponse

router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)


@router.get("/normalizations", response_model=List[SkillNormalizationResponse])
async def get_skill_normalizations(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    return await list_skill_normalizations(db)


@router.post(
    "/normalizations",
    response_model=SkillNormalizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_skill_normalization(
    payload: SkillNormalizationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    return await upsert_skill_normalization(db, payload)
