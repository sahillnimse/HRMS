"""Phase 5.1 & 5.2 endpoints: Interviews, ICS invites, Scorecard Templates, and Scorecards."""

from io import BytesIO
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.workflow import (
    create_scorecard_template,
    delete_interview,
    delete_scorecard_template,
    get_interview_detail,
    get_interview_scorecards_for_user,
    list_my_interviews,
    list_scorecard_templates,
    submit_scorecard,
    update_interview,
    update_scorecard_template,
)
from app.models.user import User, UserRole
from app.schemas.workflow import (
    InterviewParticipantOut,
    InterviewResponse,
    InterviewScorecardsResponse,
    InterviewUpdate,
    ScorecardItemResponse,
    ScorecardSubmit,
    ScorecardTemplateCreate,
    ScorecardTemplateResponse,
    ScorecardTemplateUpdate,
)
from app.services.calendar import calendar_provider

interviews_router = APIRouter()
scorecard_templates_router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


@interviews_router.get("/mine", response_model=List[InterviewResponse])
async def get_my_interviews(
    blind: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """List interviews where the current user is a participant or organizer."""
    return await list_my_interviews(db, current_user.id, blind=blind, viewer_user=current_user)


@interviews_router.get("/interviewers", response_model=List[InterviewParticipantOut])
async def list_assignable_interviewers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """List active workspace users who can be assigned as interview participants."""
    rows = (
        await db.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.full_name.asc())
        )
    ).scalars().all()
    return [
        InterviewParticipantOut(
            user_id=u.id,
            full_name=u.full_name,
            email=u.email,
            role=u.role.value,
        )
        for u in rows
    ]


@interviews_router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview_endpoint(
    interview_id: UUID,
    blind: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    iv = await get_interview_detail(db, interview_id, blind=blind, viewer_user=current_user)
    if not iv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return iv


@interviews_router.patch("/{interview_id}", response_model=InterviewResponse)
async def update_interview_endpoint(
    interview_id: UUID,
    payload: InterviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    updated = await update_interview(db, interview_id, payload, actor_id=current_user.id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return updated


@interviews_router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview_endpoint(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    ok = await delete_interview(db, interview_id, actor_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return None


@interviews_router.get("/{interview_id}/ics")
async def download_interview_ics(
    interview_id: UUID,
    blind: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Download an RFC 5545 .ics calendar invite via the configured CalendarProvider."""
    iv = await get_interview_detail(db, interview_id, blind=blind)
    if not iv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    summary = f"Interview ({iv.round_name}): {iv.candidate_name or 'Candidate'} — {iv.job_title or 'Role'}"
    desc = (
        f"Round: {iv.round_name}\n"
        f"Mode: {iv.mode}\n"
        f"Location / Link: {iv.location_or_link or 'TBD'}"
    )
    attendees = [p.email for p in iv.participants if p.email]
    ics_bytes = calendar_provider.build_invite(
        uid=str(iv.id),
        summary=summary,
        description=desc,
        start_utc=iv.scheduled_at,
        duration_minutes=iv.duration_minutes,
        location=iv.location_or_link or iv.mode,
        attendee_emails=attendees,
    )
    return StreamingResponse(
        BytesIO(ics_bytes),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="interview-{str(iv.id)[:8]}.ics"'},
    )


@interviews_router.get("/{interview_id}/scorecards", response_model=InterviewScorecardsResponse)
async def get_interview_scorecards_endpoint(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """
    Return scorecards for an interview enforcing blind-interviewer & role visibility:
    - viewer: aggregates only
    - assigned interviewer before submitting: peer scorecards locked
    - admin / non-participant recruiter / submitted interviewer: all scorecards + aggregate
    """
    res = await get_interview_scorecards_for_user(db, interview_id, current_user)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return res


@interviews_router.post(
    "/{interview_id}/scorecards",
    response_model=ScorecardItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_scorecard_endpoint(
    interview_id: UUID,
    payload: ScorecardSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    sc = await submit_scorecard(db, interview_id, current_user, payload)
    if not sc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return sc


# ---------------------------------------------------------------------------
# Scorecard Templates (admin writes, all roles read)
# ---------------------------------------------------------------------------

@scorecard_templates_router.get("/", response_model=List[ScorecardTemplateResponse])
async def list_scorecard_templates_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    return await list_scorecard_templates(db)


@scorecard_templates_router.post(
    "/",
    response_model=ScorecardTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scorecard_template_endpoint(
    payload: ScorecardTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    try:
        return await create_scorecard_template(db, payload)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scorecard template with that name already exists",
        )


@scorecard_templates_router.put("/{template_id}", response_model=ScorecardTemplateResponse)
async def update_scorecard_template_endpoint(
    template_id: UUID,
    payload: ScorecardTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    updated = await update_scorecard_template(db, template_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return updated


@scorecard_templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scorecard_template_endpoint(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    ok = await delete_scorecard_template(db, template_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return None
