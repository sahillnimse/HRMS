"""Phase 5 async CRUD: Interviews, Scorecards (with blind-peer visibility), Emails, and Offers."""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.candidate import Candidate
from app.models.pipeline import Application, ApplicationEvent, ApplicationStage
from app.models.user import User, UserRole
from app.models.workflow import (
    EmailLog,
    EmailStatus,
    EmailTemplate,
    Interview,
    InterviewParticipant,
    Offer,
    OfferStatus,
    Scorecard,
    ScorecardTemplate,
)
from app.schemas.workflow import (
    EmailLogResponse,
    EmailPreviewResponse,
    EmailSendRequest,
    EmailTemplateCreate,
    EmailTemplateUpdate,
    InterviewCreate,
    InterviewParticipantOut,
    InterviewResponse,
    InterviewScorecardsResponse,
    InterviewUpdate,
    OfferCreate,
    OfferResponse,
    OfferUpdate,
    ScorecardAggregate,
    ScorecardItemResponse,
    ScorecardSubmit,
    ScorecardTemplateCreate,
    ScorecardTemplateUpdate,
)
from app.services.audit import _mask_tokens_in_text, blind_candidate_label, record_audit
from app.services.email_sender import EmailSender, email_sender as default_email_sender, render_email_template


# ---------------------------------------------------------------------------
# Scorecard aggregation helpers
# ---------------------------------------------------------------------------

def _scorecard_avg(ratings: dict) -> Optional[float]:
    nums = [float(v) for v in (ratings or {}).values() if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def compute_scorecard_aggregate(scorecards: Sequence[Scorecard]) -> ScorecardAggregate:
    recs = {"strong_no": 0, "no": 0, "yes": 0, "strong_yes": 0}
    avgs: list[float] = []
    scale = 5
    for sc in scorecards:
        if sc.recommendation in recs:
            recs[sc.recommendation] += 1
        avg = _scorecard_avg(sc.ratings or {})
        if avg is not None:
            avgs.append(avg)
        if sc.template is not None and sc.template.scale:
            scale = sc.template.scale
    return ScorecardAggregate(
        count=len(scorecards),
        average_rating=round(sum(avgs) / len(avgs), 2) if avgs else None,
        scale=scale,
        recommendations=recs,
    )


async def get_application_scorecard_aggregates(
    db: AsyncSession,
    application_ids: Sequence[UUID],
) -> Dict[UUID, ScorecardAggregate]:
    """Batch compute scorecard aggregates per application for Kanban & Candidate views."""
    if not application_ids:
        return {}
    rows = (
        await db.execute(
            select(Interview)
            .options(selectinload(Interview.scorecards).selectinload(Scorecard.template))
            .where(Interview.application_id.in_(list(application_ids)))
        )
    ).scalars().all()
    by_app: Dict[UUID, list[Scorecard]] = {}
    for iv in rows:
        by_app.setdefault(iv.application_id, []).extend(iv.scorecards or [])
    return {aid: compute_scorecard_aggregate(scs) for aid, scs in by_app.items()}


async def get_candidate_scorecard_summary(
    db: AsyncSession,
    candidate_id: UUID,
) -> ScorecardAggregate:
    app_ids = list(
        (await db.execute(select(Application.id).where(Application.candidate_id == candidate_id)))
        .scalars()
        .all()
    )
    if not app_ids:
        return ScorecardAggregate()
    ivs = (
        await db.execute(
            select(Interview)
            .options(selectinload(Interview.scorecards).selectinload(Scorecard.template))
            .where(Interview.application_id.in_(app_ids))
        )
    ).scalars().all()
    all_scs = [sc for iv in ivs for sc in (iv.scorecards or [])]
    return compute_scorecard_aggregate(all_scs)


# ---------------------------------------------------------------------------
# Interviews
# ---------------------------------------------------------------------------

def _to_interview_response(
    iv: Interview,
    *,
    blind: bool = False,
    viewer_user: Optional[User] = None,
) -> InterviewResponse:
    app_obj = iv.application
    cand = app_obj.candidate if app_obj else None
    job = app_obj.job if app_obj else None
    cand_name = (
        blind_candidate_label(cand.id)
        if (blind and cand is not None)
        else (cand.full_name if cand is not None else None)
    )
    participants = [
        InterviewParticipantOut(
            user_id=p.user_id,
            full_name=p.user.full_name if p.user else "",
            email=p.user.email if p.user else "",
            role=p.user.role.value if p.user else "",
        )
        for p in (iv.participants or [])
    ]
    all_scs = list(iv.scorecards or [])
    agg = compute_scorecard_aggregate(all_scs)
    if viewer_user is not None and viewer_user.role != UserRole.admin:
        participant_ids = {p.user_id for p in (iv.participants or [])}
        has_submitted = any(s.interviewer_id == viewer_user.id for s in all_scs)
        if viewer_user.id in participant_ids and not has_submitted:
            # Do not leak peer ratings or recommendation spread before this interviewer submits
            agg = ScorecardAggregate(count=agg.count, scale=agg.scale)

    return InterviewResponse(
        id=iv.id,
        application_id=iv.application_id,
        candidate_id=cand.id if cand else None,
        candidate_name=cand_name,
        job_id=job.id if job else None,
        job_title=job.title if job else None,
        round_name=iv.round_name,
        scheduled_at=iv.scheduled_at,
        duration_minutes=iv.duration_minutes,
        mode=iv.mode,
        location_or_link=iv.location_or_link,
        status=iv.status,
        created_by=iv.created_by,
        created_at=iv.created_at,
        updated_at=iv.updated_at,
        participants=participants,
        scorecard_aggregate=agg,
    )


async def _load_interview(db: AsyncSession, interview_id: UUID) -> Optional[Interview]:
    res = await db.execute(
        select(Interview)
        .options(
            selectinload(Interview.application).selectinload(Application.candidate),
            selectinload(Interview.application).selectinload(Application.job),
            selectinload(Interview.participants).selectinload(InterviewParticipant.user),
            selectinload(Interview.scorecards).selectinload(Scorecard.interviewer),
            selectinload(Interview.scorecards).selectinload(Scorecard.template),
        )
        .where(Interview.id == interview_id)
    )
    return res.scalar_one_or_none()


async def create_interview(
    db: AsyncSession,
    application_id: UUID,
    payload: InterviewCreate,
    *,
    actor_id: UUID,
) -> Optional[InterviewResponse]:
    app_obj = (
        await db.execute(select(Application).where(Application.id == application_id))
    ).scalar_one_or_none()
    if not app_obj:
        return None

    sched_utc = (
        payload.scheduled_at.astimezone(timezone.utc)
        if payload.scheduled_at.tzinfo
        else payload.scheduled_at.replace(tzinfo=timezone.utc)
    )
    iv = Interview(
        application_id=application_id,
        round_name=payload.round_name.strip(),
        scheduled_at=sched_utc,
        duration_minutes=payload.duration_minutes,
        mode=payload.mode.value,
        location_or_link=payload.location_or_link.strip(),
        created_by=actor_id,
    )
    db.add(iv)
    await db.flush()

    unique_pids = list(dict.fromkeys(payload.participant_ids or [actor_id]))
    valid_users = set(
        (await db.execute(select(User.id).where(User.id.in_(unique_pids)))).scalars().all()
    )
    for uid in unique_pids:
        if uid in valid_users:
            db.add(InterviewParticipant(interview_id=iv.id, user_id=uid))

    await record_audit(
        db,
        user_id=actor_id,
        action="interview_scheduled",
        entity="interview",
        entity_id=iv.id,
        metadata={
            "application_id": str(application_id),
            "round_name": iv.round_name,
            "mode": iv.mode,
        },
        commit=False,
    )
    await db.commit()
    loaded = await _load_interview(db, iv.id)
    return _to_interview_response(loaded) if loaded else None


async def list_application_interviews(
    db: AsyncSession,
    application_id: UUID,
    *,
    blind: bool = False,
    viewer_user: Optional[User] = None,
) -> List[InterviewResponse]:
    rows = (
        await db.execute(
            select(Interview)
            .options(
                selectinload(Interview.application).selectinload(Application.candidate),
                selectinload(Interview.application).selectinload(Application.job),
                selectinload(Interview.participants).selectinload(InterviewParticipant.user),
                selectinload(Interview.scorecards).selectinload(Scorecard.template),
            )
            .where(Interview.application_id == application_id)
            .order_by(Interview.scheduled_at.asc())
        )
    ).scalars().all()
    return [_to_interview_response(r, blind=blind, viewer_user=viewer_user) for r in rows]


async def list_my_interviews(
    db: AsyncSession,
    user_id: UUID,
    *,
    blind: bool = False,
    viewer_user: Optional[User] = None,
) -> List[InterviewResponse]:
    iv_ids = list(
        (
            await db.execute(
                select(InterviewParticipant.interview_id).where(
                    InterviewParticipant.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    stmt = (
        select(Interview)
        .options(
            selectinload(Interview.application).selectinload(Application.candidate),
            selectinload(Interview.application).selectinload(Application.job),
            selectinload(Interview.participants).selectinload(InterviewParticipant.user),
            selectinload(Interview.scorecards).selectinload(Scorecard.template),
        )
        .where((Interview.id.in_(iv_ids)) | (Interview.created_by == user_id))
        .order_by(Interview.scheduled_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_interview_response(r, blind=blind, viewer_user=viewer_user) for r in rows]


async def get_interview_detail(
    db: AsyncSession,
    interview_id: UUID,
    *,
    blind: bool = False,
    viewer_user: Optional[User] = None,
) -> Optional[InterviewResponse]:
    iv = await _load_interview(db, interview_id)
    return _to_interview_response(iv, blind=blind, viewer_user=viewer_user) if iv else None


async def update_interview(
    db: AsyncSession,
    interview_id: UUID,
    payload: InterviewUpdate,
    *,
    actor_id: UUID,
) -> Optional[InterviewResponse]:
    iv = await _load_interview(db, interview_id)
    if not iv:
        return None
    data = payload.model_dump(exclude_unset=True)
    participant_ids = data.pop("participant_ids", None)
    if "scheduled_at" in data and data["scheduled_at"] is not None:
        dt = data["scheduled_at"]
        data["scheduled_at"] = (
            dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        )
    if "mode" in data and data["mode"] is not None:
        data["mode"] = data["mode"].value
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value
    for k, v in data.items():
        setattr(iv, k, v)

    if participant_ids is not None:
        await db.execute(
            delete(InterviewParticipant).where(InterviewParticipant.interview_id == iv.id)
        )
        unique_pids = list(dict.fromkeys(participant_ids))
        valid_users = set(
            (await db.execute(select(User.id).where(User.id.in_(unique_pids)))).scalars().all()
        )
        for uid in unique_pids:
            if uid in valid_users:
                db.add(InterviewParticipant(interview_id=iv.id, user_id=uid))

    await record_audit(
        db,
        user_id=actor_id,
        action="edit",
        entity="interview",
        entity_id=iv.id,
        metadata={"updated_fields": sorted(payload.model_dump(exclude_unset=True).keys())},
        commit=False,
    )
    await db.commit()
    reloaded = await _load_interview(db, iv.id)
    return _to_interview_response(reloaded) if reloaded else None


async def delete_interview(
    db: AsyncSession,
    interview_id: UUID,
    *,
    actor_id: UUID,
) -> bool:
    iv = (await db.execute(select(Interview).where(Interview.id == interview_id))).scalar_one_or_none()
    if not iv:
        return False
    await db.delete(iv)
    await record_audit(
        db,
        user_id=actor_id,
        action="delete",
        entity="interview",
        entity_id=interview_id,
        metadata={},
        commit=False,
    )
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Scorecards & Templates (with strict visibility rules)
# ---------------------------------------------------------------------------

async def list_scorecard_templates(db: AsyncSession) -> List[ScorecardTemplate]:
    return list(
        (await db.execute(select(ScorecardTemplate).order_by(ScorecardTemplate.name.asc())))
        .scalars()
        .all()
    )


async def create_scorecard_template(
    db: AsyncSession, payload: ScorecardTemplateCreate
) -> ScorecardTemplate:
    tpl = ScorecardTemplate(
        name=payload.name.strip(),
        competencies=[c.model_dump() for c in payload.competencies],
        scale=payload.scale,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


async def update_scorecard_template(
    db: AsyncSession, template_id: UUID, payload: ScorecardTemplateUpdate
) -> Optional[ScorecardTemplate]:
    tpl = (
        await db.execute(select(ScorecardTemplate).where(ScorecardTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        data["name"] = data["name"].strip()
    if "competencies" in data and data["competencies"] is not None:
        data["competencies"] = [
            c.model_dump() if hasattr(c, "model_dump") else c for c in data["competencies"]
        ]
    for k, v in data.items():
        setattr(tpl, k, v)
    await db.commit()
    await db.refresh(tpl)
    return tpl


async def delete_scorecard_template(db: AsyncSession, template_id: UUID) -> bool:
    tpl = (
        await db.execute(select(ScorecardTemplate).where(ScorecardTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        return False
    await db.delete(tpl)
    await db.commit()
    return True


def _to_scorecard_item(sc: Scorecard) -> ScorecardItemResponse:
    return ScorecardItemResponse(
        id=sc.id,
        interview_id=sc.interview_id,
        interviewer_id=sc.interviewer_id,
        interviewer_name=sc.interviewer.full_name if sc.interviewer else None,
        interviewer_email=sc.interviewer.email if sc.interviewer else None,
        template_id=sc.template_id,
        ratings=sc.ratings or {},
        average_rating=_scorecard_avg(sc.ratings or {}),
        recommendation=sc.recommendation,
        comments=sc.comments or "",
        submitted_at=sc.submitted_at,
    )


async def get_interview_scorecards_for_user(
    db: AsyncSession,
    interview_id: UUID,
    current_user: User,
) -> Optional[InterviewScorecardsResponse]:
    """
    Visibility rules:
      - viewer: sees aggregate ONLY (never individual scorecards).
      - admin: sees all scorecards + aggregate.
      - assigned participant (non-admin): cannot see other interviewers' scorecards
        until they have submitted their own scorecard.
      - recruiter (non-participant or after submitting own): sees all scorecards + aggregate.
    """
    iv = await _load_interview(db, interview_id)
    if not iv:
        return None

    all_scs = list(iv.scorecards or [])
    agg = compute_scorecard_aggregate(all_scs)
    participant_ids = {p.user_id for p in (iv.participants or [])}
    my_sc = next((s for s in all_scs if s.interviewer_id == current_user.id), None)
    my_submitted = my_sc is not None

    if current_user.role == UserRole.viewer:
        return InterviewScorecardsResponse(
            interview_id=interview_id,
            aggregate=agg,
            scorecards=[],
            peer_scorecards_locked=False,
            viewer_aggregate_only=True,
            my_submitted=False,
        )

    is_assigned_interviewer = current_user.id in participant_ids
    if current_user.role != UserRole.admin and is_assigned_interviewer and not my_submitted:
        return InterviewScorecardsResponse(
            interview_id=interview_id,
            aggregate=ScorecardAggregate(count=agg.count, scale=agg.scale),
            scorecards=[],
            peer_scorecards_locked=True,
            viewer_aggregate_only=False,
            my_submitted=False,
        )

    return InterviewScorecardsResponse(
        interview_id=interview_id,
        aggregate=agg,
        scorecards=[_to_scorecard_item(s) for s in all_scs],
        peer_scorecards_locked=False,
        viewer_aggregate_only=False,
        my_submitted=my_submitted,
    )


async def submit_scorecard(
    db: AsyncSession,
    interview_id: UUID,
    interviewer: User,
    payload: ScorecardSubmit,
) -> Optional[ScorecardItemResponse]:
    iv = (await db.execute(select(Interview).where(Interview.id == interview_id))).scalar_one_or_none()
    if not iv:
        return None

    now = datetime.now(timezone.utc)
    upsert = (
        pg_insert(Scorecard)
        .values(
            interview_id=interview_id,
            interviewer_id=interviewer.id,
            template_id=payload.template_id,
            ratings=payload.ratings,
            recommendation=payload.recommendation.value,
            comments=payload.comments.strip(),
            submitted_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_scorecards_interview_interviewer",
            set_={
                "template_id": payload.template_id,
                "ratings": payload.ratings,
                "recommendation": payload.recommendation.value,
                "comments": payload.comments.strip(),
                "submitted_at": now,
                "updated_at": now,
            },
        )
    )
    await db.execute(upsert)
    await record_audit(
        db,
        user_id=interviewer.id,
        action="scorecard_submitted",
        entity="interview",
        entity_id=interview_id,
        metadata={"recommendation": payload.recommendation.value},
        commit=False,
    )
    await db.commit()

    sc = (
        await db.execute(
            select(Scorecard)
            .options(selectinload(Scorecard.interviewer))
            .where(
                Scorecard.interview_id == interview_id,
                Scorecard.interviewer_id == interviewer.id,
            )
        )
    ).scalar_one()
    return _to_scorecard_item(sc)


# ---------------------------------------------------------------------------
# Email Templates & Sending
# ---------------------------------------------------------------------------

async def list_email_templates(db: AsyncSession) -> List[EmailTemplate]:
    return list(
        (await db.execute(select(EmailTemplate).order_by(EmailTemplate.key.asc()))).scalars().all()
    )


async def create_email_template(
    db: AsyncSession, payload: EmailTemplateCreate
) -> EmailTemplate:
    # Rejection templates MUST never auto-send (always manual confirmation)
    is_rejection = (payload.stage_trigger or "").lower() == "rejected" or "reject" in payload.key.lower()
    tpl = EmailTemplate(
        key=payload.key.strip().lower(),
        subject=payload.subject.strip(),
        body=payload.body,
        stage_trigger=payload.stage_trigger,
        auto_send=False if is_rejection else bool(payload.auto_send),
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


async def update_email_template(
    db: AsyncSession, template_id: UUID, payload: EmailTemplateUpdate
) -> Optional[EmailTemplate]:
    tpl = (
        await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        return None
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(tpl, k, v)
    # Enforce rejection manual-confirmation invariant
    if (tpl.stage_trigger or "").lower() == "rejected" or "reject" in tpl.key.lower():
        tpl.auto_send = False
    await db.commit()
    await db.refresh(tpl)
    return tpl


async def delete_email_template(db: AsyncSession, template_id: UUID) -> bool:
    tpl = (
        await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        return False
    await db.delete(tpl)
    await db.commit()
    return True


async def build_email_preview(
    db: AsyncSession,
    *,
    candidate_id: UUID,
    application_id: Optional[UUID] = None,
    template_key: Optional[str] = None,
    subject_override: Optional[str] = None,
    body_override: Optional[str] = None,
    extra_vars: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[EmailPreviewResponse], Optional[str]]:
    cand = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
    if not cand:
        return None, "candidate_not_found"

    tpl: Optional[EmailTemplate] = None
    if template_key:
        tpl = (
            await db.execute(select(EmailTemplate).where(EmailTemplate.key == template_key))
        ).scalar_one_or_none()
        if not tpl and not (subject_override and body_override):
            return None, "template_not_found"

    job_title = ""
    stage_val = ""
    if application_id:
        app_obj = (
            await db.execute(
                select(Application)
                .options(selectinload(Application.job))
                .where(Application.id == application_id)
            )
        ).scalar_one_or_none()
        if app_obj:
            job_title = app_obj.job.title if app_obj.job else ""
            stage_val = app_obj.stage.value

    variables: Dict[str, str] = {
        "candidate_name": cand.full_name,
        "job_title": job_title or "the open role",
        "stage": stage_val,
        "company_name": settings.APP_NAME,
        "round_name": "Interview",
        "interview_time": "TBD",
        "interview_link": "TBD",
    }
    if extra_vars:
        variables.update(extra_vars)

    raw_subject = subject_override if subject_override is not None else (tpl.subject if tpl else "")
    raw_body = body_override if body_override is not None else (tpl.body if tpl else "")

    return (
        EmailPreviewResponse(
            to=cand.email,
            subject=render_email_template(raw_subject, variables),
            body=render_email_template(raw_body, variables),
            template_key=template_key,
        ),
        None,
    )


async def send_candidate_email(
    db: AsyncSession,
    payload: EmailSendRequest,
    *,
    actor_id: UUID,
    sender: Optional[EmailSender] = None,
) -> Tuple[Optional[EmailLogResponse], Optional[str]]:
    # Rejection emails always require explicit manual confirmation (by key OR stage_trigger)
    is_rejection_email = bool(payload.template_key and "reject" in payload.template_key.lower())
    if payload.template_key and not is_rejection_email:
        tpl_row = (
            await db.execute(
                select(EmailTemplate).where(EmailTemplate.key == payload.template_key)
            )
        ).scalar_one_or_none()
        if tpl_row is not None and (tpl_row.stage_trigger or "").lower() == "rejected":
            is_rejection_email = True
    if is_rejection_email and not payload.confirm_rejection:
        return None, "rejection_confirmation_required"

    preview, err = await build_email_preview(
        db,
        candidate_id=payload.candidate_id,
        application_id=payload.application_id,
        template_key=payload.template_key,
        subject_override=payload.subject,
        body_override=payload.body,
        extra_vars=payload.extra_vars,
    )
    if err or not preview:
        return None, err or "preview_failed"

    recipient = str(payload.to) if payload.to else (preview.to or "")
    if not recipient:
        return None, "missing_recipient_email"
    if not preview.subject.strip():
        return None, "missing_subject"

    log_entry = EmailLog(
        candidate_id=payload.candidate_id,
        application_id=payload.application_id,
        template_key=payload.template_key,
        to_email=recipient,
        subject=preview.subject.strip(),
        status=EmailStatus.queued.value,
        created_by=actor_id,
    )
    db.add(log_entry)
    await db.flush()

    transport = sender or default_email_sender
    try:
        await transport.send_email(
            to_email=recipient,
            subject=preview.subject.strip(),
            body=preview.body,
        )
        log_entry.status = EmailStatus.sent.value
    except Exception as exc:
        log_entry.status = EmailStatus.failed.value
        log_entry.error = str(exc)[:500]

    await record_audit(
        db,
        user_id=actor_id,
        action="email_sent",
        entity="candidate",
        entity_id=payload.candidate_id,
        metadata={
            "email_log_id": str(log_entry.id),
            "template_key": payload.template_key,
            "status": log_entry.status,
            "subject": log_entry.subject,
        },
        commit=False,
    )
    await db.commit()
    await db.refresh(log_entry)

    actor = (await db.execute(select(User).where(User.id == actor_id))).scalar_one_or_none()
    return (
        EmailLogResponse(
            id=log_entry.id,
            candidate_id=log_entry.candidate_id,
            application_id=log_entry.application_id,
            template_key=log_entry.template_key,
            to=log_entry.to_email,
            subject=log_entry.subject,
            status=log_entry.status,
            error=log_entry.error,
            created_by=log_entry.created_by,
            actor_name=actor.full_name if actor else None,
            created_at=log_entry.created_at,
        ),
        None,
    )


async def list_candidate_emails(
    db: AsyncSession,
    candidate_id: UUID,
    *,
    blind: bool = False,
) -> List[EmailLogResponse]:
    rows = (
        await db.execute(
            select(EmailLog)
            .options(selectinload(EmailLog.actor))
            .where(EmailLog.candidate_id == candidate_id)
            .order_by(EmailLog.created_at.desc())
        )
    ).scalars().all()

    mask_tokens: list[str] = []
    if blind and rows:
        cand = (
            await db.execute(select(Candidate).where(Candidate.id == candidate_id))
        ).scalar_one_or_none()
        if cand is not None:
            if cand.full_name:
                mask_tokens.append(cand.full_name)
                mask_tokens.extend(p for p in cand.full_name.split() if len(p) >= 3)
            if cand.email:
                mask_tokens.append(cand.email)

    return [
        EmailLogResponse(
            id=r.id,
            candidate_id=r.candidate_id,
            application_id=r.application_id,
            template_key=r.template_key,
            to="[Redacted]" if blind else r.to_email,
            subject=_mask_tokens_in_text(r.subject, mask_tokens) if blind else r.subject,
            status=r.status,
            error=r.error,
            created_by=r.created_by,
            actor_name=r.actor.full_name if r.actor else None,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Offers (admin / recruiter ONLY; synced with Application.stage)
# ---------------------------------------------------------------------------

def _to_offer_response(o: Offer) -> OfferResponse:
    app_obj = o.application
    cand = app_obj.candidate if app_obj else None
    job = app_obj.job if app_obj else None
    return OfferResponse(
        id=o.id,
        application_id=o.application_id,
        candidate_id=cand.id if cand else None,
        candidate_name=cand.full_name if cand else None,
        job_id=job.id if job else None,
        job_title=job.title if job else None,
        offered_ctc=float(o.offered_ctc),
        currency=o.currency,
        status=o.status,
        expected_joining_date=o.expected_joining_date,
        decline_reason=o.decline_reason,
        notes=o.notes or "",
        created_by=o.created_by,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


async def _sync_stage_for_offer_status(
    db: AsyncSession,
    app_obj: Application,
    offer_status: OfferStatus,
    actor_id: UUID,
) -> None:
    target_stage: Optional[ApplicationStage] = None
    reason: Optional[str] = None
    if offer_status == OfferStatus.extended and app_obj.stage in (
        ApplicationStage.applied,
        ApplicationStage.screened,
        ApplicationStage.interview,
    ):
        target_stage = ApplicationStage.offer
        reason = "Offer extended"
    elif offer_status == OfferStatus.accepted and app_obj.stage != ApplicationStage.hired:
        target_stage = ApplicationStage.hired
        reason = "Offer accepted"

    if target_stage is not None:
        prev = app_obj.stage.value
        app_obj.stage = target_stage
        app_obj.stage_changed_at = datetime.now(timezone.utc)
        db.add(
            ApplicationEvent(
                application_id=app_obj.id,
                from_stage=prev,
                to_stage=target_stage.value,
                changed_by=actor_id,
                reason=reason,
            )
        )


async def create_offer(
    db: AsyncSession,
    application_id: UUID,
    payload: OfferCreate,
    *,
    actor_id: UUID,
) -> Optional[OfferResponse]:
    app_obj = (
        await db.execute(
            select(Application)
            .options(selectinload(Application.candidate), selectinload(Application.job))
            .where(Application.id == application_id)
        )
    ).scalar_one_or_none()
    if not app_obj:
        return None

    joining_date = payload.expected_joining_date
    if joining_date is None and app_obj.candidate and app_obj.candidate.notice_period_days is not None:
        joining_date = date.today() + timedelta(days=int(app_obj.candidate.notice_period_days))

    offer = Offer(
        application_id=application_id,
        offered_ctc=payload.offered_ctc,
        currency=payload.currency.strip().upper(),
        status=payload.status.value,
        expected_joining_date=joining_date,
        decline_reason=payload.decline_reason,
        notes=payload.notes.strip(),
        created_by=actor_id,
    )
    db.add(offer)
    await db.flush()

    await _sync_stage_for_offer_status(db, app_obj, payload.status, actor_id)
    await record_audit(
        db,
        user_id=actor_id,
        action="offer_created",
        entity="offer",
        entity_id=offer.id,
        metadata={"application_id": str(application_id), "status": offer.status},
        commit=False,
    )
    await db.commit()
    loaded = (
        await db.execute(
            select(Offer)
            .options(
                selectinload(Offer.application).selectinload(Application.candidate),
                selectinload(Offer.application).selectinload(Application.job),
            )
            .where(Offer.id == offer.id)
        )
    ).scalar_one()
    return _to_offer_response(loaded)


async def list_application_offers(db: AsyncSession, application_id: UUID) -> List[OfferResponse]:
    rows = (
        await db.execute(
            select(Offer)
            .options(
                selectinload(Offer.application).selectinload(Application.candidate),
                selectinload(Offer.application).selectinload(Application.job),
            )
            .where(Offer.application_id == application_id)
            .order_by(Offer.created_at.desc())
        )
    ).scalars().all()
    return [_to_offer_response(r) for r in rows]


async def update_offer(
    db: AsyncSession,
    offer_id: UUID,
    payload: OfferUpdate,
    *,
    actor_id: UUID,
) -> Optional[OfferResponse]:
    offer = (
        await db.execute(
            select(Offer)
            .options(
                selectinload(Offer.application).selectinload(Application.candidate),
                selectinload(Offer.application).selectinload(Application.job),
            )
            .where(Offer.id == offer_id)
        )
    ).scalar_one_or_none()
    if not offer:
        return None

    data = payload.model_dump(exclude_unset=True)
    if "currency" in data and data["currency"]:
        data["currency"] = data["currency"].strip().upper()
    new_status: Optional[OfferStatus] = data.get("status")
    if new_status is not None:
        data["status"] = new_status.value
    for k, v in data.items():
        setattr(offer, k, v)

    if new_status is not None and offer.application is not None:
        await _sync_stage_for_offer_status(db, offer.application, new_status, actor_id)

    await record_audit(
        db,
        user_id=actor_id,
        action="offer_updated",
        entity="offer",
        entity_id=offer.id,
        metadata={"status": offer.status},
        commit=False,
    )
    await db.commit()
    await db.refresh(offer)
    return _to_offer_response(offer)


async def delete_offer(db: AsyncSession, offer_id: UUID, *, actor_id: UUID) -> bool:
    offer = (await db.execute(select(Offer).where(Offer.id == offer_id))).scalar_one_or_none()
    if not offer:
        return False
    await db.delete(offer)
    await record_audit(
        db,
        user_id=actor_id,
        action="delete",
        entity="offer",
        entity_id=offer_id,
        metadata={},
        commit=False,
    )
    await db.commit()
    return True
