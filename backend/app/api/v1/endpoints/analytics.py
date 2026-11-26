"""
Phase 6 Analytics endpoints (admin / recruiter / viewer read-only).

All metrics are derived directly from existing ApplicationEvent stage history,
Application, Job, and Candidate.source without duplicating data.

GET /api/v1/analytics/funnel
GET /api/v1/analytics/time-in-stage
GET /api/v1/analytics/time-to-hire
GET /api/v1/analytics/sources
GET /api/v1/analytics/stuck
"""

from datetime import date
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.models.user import User, UserRole
from app.schemas.analytics import (
    FunnelAnalyticsResponse,
    SourcesAnalyticsResponse,
    StuckCandidatesResponse,
    TimeInStageResponse,
    TimeToHireResponse,
)
from app.services.analytics import (
    get_funnel_analytics,
    get_source_analytics,
    get_stuck_applications,
    get_time_in_stage_analytics,
    get_time_to_hire_analytics,
)

router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)


@router.get("/funnel", response_model=FunnelAnalyticsResponse)
async def analytics_funnel(
    job_id: Optional[UUID] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(*READ_ROLES)),
):
    return await get_funnel_analytics(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )


@router.get("/time-in-stage", response_model=TimeInStageResponse)
async def analytics_time_in_stage(
    job_id: Optional[UUID] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(*READ_ROLES)),
):
    return await get_time_in_stage_analytics(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )


@router.get("/time-to-hire", response_model=TimeToHireResponse)
async def analytics_time_to_hire(
    job_id: Optional[UUID] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(*READ_ROLES)),
):
    return await get_time_to_hire_analytics(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )


@router.get("/sources", response_model=SourcesAnalyticsResponse)
async def analytics_sources(
    job_id: Optional[UUID] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(*READ_ROLES)),
):
    return await get_source_analytics(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )


@router.get("/stuck", response_model=StuckCandidatesResponse)
async def analytics_stuck(
    job_id: Optional[UUID] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    applied_days: Optional[int] = Query(default=None, ge=1, le=365),
    screened_days: Optional[int] = Query(default=None, ge=1, le=365),
    interview_days: Optional[int] = Query(default=None, ge=1, le=365),
    offer_days: Optional[int] = Query(default=None, ge=1, le=365),
    blind: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(*READ_ROLES)),
):
    overrides: Dict[str, int] = {}
    if applied_days is not None:
        overrides["applied"] = applied_days
    if screened_days is not None:
        overrides["screened"] = screened_days
    if interview_days is not None:
        overrides["interview"] = interview_days
    if offer_days is not None:
        overrides["offer"] = offer_days

    return await get_stuck_applications(
        db,
        job_id=job_id,
        start_date=start_date,
        end_date=end_date,
        thresholds_override=overrides or None,
        blind=blind,
    )
