"""Privacy, retention policy, and admin data-purge endpoints (Phase 3)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.config import settings
from app.models.user import User, UserRole
from app.schemas.candidate import RetentionPurgeResponse
from app.services.cleanup import purge_expired_candidates

router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)


@router.get("/settings", response_model=dict)
async def get_privacy_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Return current retention & privacy configuration plus count of candidates past retention."""
    expired_count, _ = await purge_expired_candidates(
        db,
        retention_days=settings.RETENTION_DAYS,
        dry_run=True,
    )
    return {
        "retention_days": settings.RETENTION_DAYS,
        "orphan_max_age_hours": settings.ORPHAN_MAX_AGE_HOURS,
        "ocr_fallback_enabled": settings.ENABLE_OCR_FALLBACK,
        "semantic_search_enabled": settings.ENABLE_SEMANTIC_SEARCH,
        "expired_candidates_count": expired_count,
    }


@router.post("/purge-expired", response_model=RetentionPurgeResponse)
async def run_retention_purge(
    retention_days: Optional[int] = Query(None, ge=0),
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    Admin-only: purge candidates exceeding `retention_days` (default: `RETENTION_DAYS`),
    removing resume files and all PII while retaining PII-free audit entries.
    """
    effective_days = settings.RETENTION_DAYS if retention_days is None else retention_days
    count, ids = await purge_expired_candidates(
        db,
        retention_days=effective_days,
        actor_id=current_user.id,
        dry_run=dry_run,
    )
    return RetentionPurgeResponse(
        retention_days=effective_days,
        dry_run=dry_run,
        matched_count=count,
        purged_count=0 if dry_run else count,
        candidate_ids=ids,
    )
