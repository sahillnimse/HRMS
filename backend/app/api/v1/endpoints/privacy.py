"""Privacy, retention policy, admin data-purge, and India DPDP Act erasure-request endpoints."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.config import settings
from app.crud.backlog import (
    create_erasure_request,
    execute_erasure_request,
    list_erasure_requests,
)
from app.models.user import User, UserRole
from app.schemas.backlog import ErasureRequestCreate, ErasureRequestResponse
from app.schemas.candidate import RetentionPurgeResponse
from app.services.cleanup import purge_expired_candidates

router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


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


@router.get("/erasure-requests", response_model=List[ErasureRequestResponse])
async def list_erasure_requests_endpoint(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """List India DPDP Act erasure & consent-withdrawal requests."""
    return await list_erasure_requests(db, limit=limit)


@router.post(
    "/erasure-requests",
    response_model=ErasureRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_erasure_request_endpoint(
    payload: ErasureRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Log a candidate's DPDP Act erasure or consent-withdrawal request."""
    req, err = await create_erasure_request(db, payload, actor_id=current_user.id)
    if err == "candidate_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    assert req is not None
    return req


@router.post("/erasure-requests/{request_id}/execute", response_model=ErasureRequestResponse)
async def execute_erasure_request_endpoint(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """Admin-only: execute a DPDP erasure request, deleting candidate PII/files & retaining PII-free proof."""
    req, err = await execute_erasure_request(db, request_id, actor_id=current_user.id)
    if err == "request_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Erasure request not found")
    assert req is not None
    return req
