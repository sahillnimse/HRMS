"""Async CRUD for Jobs, Applications, ApplicationEvents, CandidateNotes, and AuditLogs."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.candidate import Candidate
from app.models.pipeline import (
    Application,
    ApplicationEvent,
    ApplicationStage,
    AuditLog,
    CandidateNote,
    Job,
    JobStatus,
)
from app.schemas.pipeline import (
    ActivityTimelineItem,
    ApplicationCardCandidate,
    ApplicationResponse,
    AuditLogResponse,
    CandidateNoteCreate,
    CandidateNoteResponse,
    JobCreate,
    JobDetailResponse,
    JobResponse,
    JobUpdate,
)
from app.services.audit import record_audit


def _clean_tags(items: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for raw in items or []:
        s = raw.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

async def create_job(db: AsyncSession, job_in: JobCreate, *, created_by: Optional[UUID]) -> Job:
    job = Job(
        title=job_in.title.strip(),
        department=job_in.department.strip(),
        location=job_in.location.strip(),
        description=job_in.description.strip(),
        required_skills=_clean_tags(job_in.required_skills),
        nice_to_have_skills=_clean_tags(job_in.nice_to_have_skills),
        min_years=job_in.min_years,
        max_years=job_in.max_years,
        status=job_in.status,
        created_by=created_by,
    )
    db.add(job)
    await db.flush()
    await record_audit(
        db,
        user_id=created_by,
        action="create",
        entity="job",
        entity_id=job.id,
        metadata={"title": job.title, "status": job.status.value},
        commit=False,
    )
    await db.commit()
    await db.refresh(job)
    return job


async def get_job_by_id(db: AsyncSession, job_id: UUID) -> Optional[Job]:
    res = await db.execute(select(Job).where(Job.id == job_id))
    return res.scalar_one_or_none()


async def list_jobs(
    db: AsyncSession,
    *,
    status_filter: Optional[JobStatus] = None,
    department: Optional[str] = None,
    search: Optional[str] = None,
) -> List[JobResponse]:
    stmt = select(Job)
    conditions = []
    if status_filter is not None:
        conditions.append(Job.status == status_filter)
    if department:
        conditions.append(Job.department.ilike(f"%{department.strip()}%"))
    if search:
        pat = f"%{search.strip()}%"
        conditions.append(
            or_(
                Job.title.ilike(pat),
                Job.department.ilike(pat),
                Job.location.ilike(pat),
            )
        )
    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(Job.created_at.desc())
    jobs = list((await db.execute(stmt)).scalars().all())
    if not jobs:
        return []

    job_ids = [j.id for j in jobs]
    counts_res = await db.execute(
        select(Application.job_id, Application.stage, func.count())
        .where(Application.job_id.in_(job_ids))
        .group_by(Application.job_id, Application.stage)
    )
    stage_map: Dict[UUID, Dict[str, int]] = {}
    for jid, stage, cnt in counts_res.all():
        stage_map.setdefault(jid, {})[stage.value] = int(cnt)

    responses: List[JobResponse] = []
    for j in jobs:
        sc = stage_map.get(j.id, {})
        resp = JobResponse.model_validate(j)
        resp.stage_counts = sc
        resp.application_count = sum(sc.values())
        responses.append(resp)
    return responses


async def get_job_detail(db: AsyncSession, job_id: UUID) -> Optional[JobDetailResponse]:
    res = await db.execute(
        select(Job)
        .options(selectinload(Job.applications).selectinload(Application.candidate))
        .where(Job.id == job_id)
    )
    job = res.scalar_one_or_none()
    if not job:
        return None

    from app.crud.workflow import get_application_scorecard_aggregates

    agg_map = await get_application_scorecard_aggregates(db, [a.id for a in job.applications])
    stage_counts: Dict[str, int] = {}
    app_items: List[ApplicationResponse] = []
    for app in sorted(job.applications, key=lambda a: a.stage_changed_at, reverse=True):
        stage_counts[app.stage.value] = stage_counts.get(app.stage.value, 0) + 1
        agg = agg_map.get(app.id)
        app_items.append(
            ApplicationResponse(
                id=app.id,
                candidate_id=app.candidate_id,
                job_id=app.job_id,
                stage=app.stage,
                stage_changed_at=app.stage_changed_at,
                rejection_reason=app.rejection_reason,
                created_at=app.created_at,
                updated_at=app.updated_at,
                candidate=(
                    ApplicationCardCandidate.model_validate(app.candidate)
                    if app.candidate is not None
                    else None
                ),
                job_title=job.title,
                job_department=job.department,
                job_status=job.status,
                scorecard_count=agg.count if agg else 0,
                scorecard_average=agg.average_rating if agg else None,
                scorecard_recommendations=agg.recommendations if agg else {},
            )
        )

    base = JobResponse.model_validate(job)
    return JobDetailResponse(
        **base.model_dump(exclude={"application_count", "stage_counts"}),
        application_count=len(app_items),
        stage_counts=stage_counts,
        applications=app_items,
    )


async def update_job(
    db: AsyncSession,
    job: Job,
    job_in: JobUpdate,
    *,
    actor_id: Optional[UUID],
) -> Job:
    data = job_in.model_dump(exclude_unset=True)
    if "required_skills" in data and data["required_skills"] is not None:
        data["required_skills"] = _clean_tags(data["required_skills"])
    if "nice_to_have_skills" in data and data["nice_to_have_skills"] is not None:
        data["nice_to_have_skills"] = _clean_tags(data["nice_to_have_skills"])
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(job, field, value)

    await record_audit(
        db,
        user_id=actor_id,
        action="edit",
        entity="job",
        entity_id=job.id,
        metadata={"updated_fields": sorted(data.keys())},
        commit=False,
    )
    await db.commit()
    await db.refresh(job)
    return job


async def delete_job(db: AsyncSession, job_id: UUID, *, actor_id: Optional[UUID]) -> bool:
    job = await get_job_by_id(db, job_id)
    if not job:
        return False
    title = job.title
    await db.delete(job)
    await record_audit(
        db,
        user_id=actor_id,
        action="delete",
        entity="job",
        entity_id=job_id,
        metadata={"title": title},
        commit=False,
    )
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Applications & Stage Transitions
# ---------------------------------------------------------------------------

async def create_application(
    db: AsyncSession,
    *,
    candidate_id: UUID,
    job_id: UUID,
    stage: ApplicationStage = ApplicationStage.applied,
    actor_id: Optional[UUID],
) -> Tuple[Optional[ApplicationResponse], Optional[str]]:
    """
    Create an Application + initial ApplicationEvent + audit_log.
    Returns (ApplicationResponse, None) or (None, error_code).
    """
    cand = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
    if not cand:
        return None, "candidate_not_found"
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if not job:
        return None, "job_not_found"

    now = datetime.now(timezone.utc)
    app_obj = Application(
        candidate_id=candidate_id,
        job_id=job_id,
        stage=stage,
        stage_changed_at=now,
        created_by=actor_id,
    )
    db.add(app_obj)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return None, "duplicate"

    db.add(
        ApplicationEvent(
            application_id=app_obj.id,
            from_stage=None,
            to_stage=stage.value,
            changed_by=actor_id,
            reason=f"Added to {job.title}",
        )
    )
    await record_audit(
        db,
        user_id=actor_id,
        action="stage_change",
        entity="application",
        entity_id=app_obj.id,
        metadata={
            "candidate_id": str(candidate_id),
            "job_id": str(job_id),
            "job_title": job.title,
            "from_stage": None,
            "to_stage": stage.value,
        },
        commit=False,
    )
    await db.commit()
    await db.refresh(app_obj)

    return (
        ApplicationResponse(
            id=app_obj.id,
            candidate_id=app_obj.candidate_id,
            job_id=app_obj.job_id,
            stage=app_obj.stage,
            stage_changed_at=app_obj.stage_changed_at,
            rejection_reason=app_obj.rejection_reason,
            created_at=app_obj.created_at,
            updated_at=app_obj.updated_at,
            candidate=ApplicationCardCandidate.model_validate(cand),
            job_title=job.title,
            job_department=job.department,
            job_status=job.status,
        ),
        None,
    )


async def move_application_stage(
    db: AsyncSession,
    application_id: UUID,
    *,
    to_stage: ApplicationStage,
    rejection_reason: Optional[str] = None,
    reason: Optional[str] = None,
    actor_id: Optional[UUID],
) -> Optional[ApplicationResponse]:
    res = await db.execute(
        select(Application)
        .options(selectinload(Application.candidate), selectinload(Application.job))
        .where(Application.id == application_id)
    )
    app_obj = res.scalar_one_or_none()
    if not app_obj:
        return None

    from_stage = app_obj.stage.value
    app_obj.stage = to_stage
    app_obj.stage_changed_at = datetime.now(timezone.utc)
    if to_stage == ApplicationStage.rejected:
        app_obj.rejection_reason = (rejection_reason or reason or "").strip() or None
    elif rejection_reason is not None:
        app_obj.rejection_reason = rejection_reason.strip() or None

    event_reason = (reason or rejection_reason or "").strip() or None
    db.add(
        ApplicationEvent(
            application_id=app_obj.id,
            from_stage=from_stage,
            to_stage=to_stage.value,
            changed_by=actor_id,
            reason=event_reason,
        )
    )
    await record_audit(
        db,
        user_id=actor_id,
        action="stage_change",
        entity="application",
        entity_id=app_obj.id,
        metadata={
            "candidate_id": str(app_obj.candidate_id),
            "job_id": str(app_obj.job_id),
            "job_title": app_obj.job.title if app_obj.job else None,
            "from_stage": from_stage,
            "to_stage": to_stage.value,
            "reason": event_reason,
        },
        commit=False,
    )
    await db.commit()
    await db.refresh(app_obj)

    return ApplicationResponse(
        id=app_obj.id,
        candidate_id=app_obj.candidate_id,
        job_id=app_obj.job_id,
        stage=app_obj.stage,
        stage_changed_at=app_obj.stage_changed_at,
        rejection_reason=app_obj.rejection_reason,
        created_at=app_obj.created_at,
        updated_at=app_obj.updated_at,
        candidate=(
            ApplicationCardCandidate.model_validate(app_obj.candidate)
            if app_obj.candidate is not None
            else None
        ),
        job_title=app_obj.job.title if app_obj.job else None,
        job_department=app_obj.job.department if app_obj.job else None,
        job_status=app_obj.job.status if app_obj.job else None,
    )


async def delete_application(
    db: AsyncSession,
    application_id: UUID,
    *,
    actor_id: Optional[UUID],
) -> bool:
    res = await db.execute(select(Application).where(Application.id == application_id))
    app_obj = res.scalar_one_or_none()
    if not app_obj:
        return False
    cand_id = str(app_obj.candidate_id)
    job_id = str(app_obj.job_id)
    await db.delete(app_obj)
    await record_audit(
        db,
        user_id=actor_id,
        action="delete",
        entity="application",
        entity_id=application_id,
        metadata={"candidate_id": cand_id, "job_id": job_id},
        commit=False,
    )
    await db.commit()
    return True


async def list_candidate_applications(
    db: AsyncSession,
    candidate_id: UUID,
) -> List[ApplicationResponse]:
    res = await db.execute(
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.candidate_id == candidate_id)
        .order_by(Application.stage_changed_at.desc())
    )
    from app.crud.workflow import get_application_scorecard_aggregates

    apps = res.scalars().all()
    agg_map = await get_application_scorecard_aggregates(db, [a.id for a in apps])
    return [
        ApplicationResponse(
            id=a.id,
            candidate_id=a.candidate_id,
            job_id=a.job_id,
            stage=a.stage,
            stage_changed_at=a.stage_changed_at,
            rejection_reason=a.rejection_reason,
            created_at=a.created_at,
            updated_at=a.updated_at,
            job_title=a.job.title if a.job else None,
            job_department=a.job.department if a.job else None,
            job_status=a.job.status if a.job else None,
            scorecard_count=agg_map[a.id].count if a.id in agg_map else 0,
            scorecard_average=agg_map[a.id].average_rating if a.id in agg_map else None,
            scorecard_recommendations=agg_map[a.id].recommendations if a.id in agg_map else {},
        )
        for a in apps
    ]


# ---------------------------------------------------------------------------
# Candidate Notes
# ---------------------------------------------------------------------------

async def list_candidate_notes(
    db: AsyncSession,
    candidate_id: UUID,
) -> List[CandidateNoteResponse]:
    res = await db.execute(
        select(CandidateNote)
        .options(selectinload(CandidateNote.author))
        .where(CandidateNote.candidate_id == candidate_id)
        .order_by(CandidateNote.created_at.desc())
    )
    notes = res.scalars().all()
    return [
        CandidateNoteResponse(
            id=n.id,
            candidate_id=n.candidate_id,
            author_id=n.author_id,
            author_name=(n.author.full_name or n.author.email) if n.author else None,
            author_email=n.author.email if n.author else None,
            body=n.body,
            tags=n.tags or [],
            created_at=n.created_at,
            updated_at=n.updated_at,
        )
        for n in notes
    ]


async def create_candidate_note(
    db: AsyncSession,
    *,
    candidate_id: UUID,
    author_id: UUID,
    note_in: CandidateNoteCreate,
) -> CandidateNoteResponse:
    note = CandidateNote(
        candidate_id=candidate_id,
        author_id=author_id,
        body=note_in.body.strip(),
        tags=_clean_tags(note_in.tags),
    )
    db.add(note)
    await db.flush()
    await record_audit(
        db,
        user_id=author_id,
        action="edit",
        entity="candidate_note",
        entity_id=note.id,
        metadata={"candidate_id": str(candidate_id), "tags": note.tags},
        commit=False,
    )
    await db.commit()

    res = await db.execute(
        select(CandidateNote)
        .options(selectinload(CandidateNote.author))
        .where(CandidateNote.id == note.id)
    )
    loaded = res.scalar_one()
    return CandidateNoteResponse(
        id=loaded.id,
        candidate_id=loaded.candidate_id,
        author_id=loaded.author_id,
        author_name=(loaded.author.full_name or loaded.author.email) if loaded.author else None,
        author_email=loaded.author.email if loaded.author else None,
        body=loaded.body,
        tags=loaded.tags or [],
        created_at=loaded.created_at,
        updated_at=loaded.updated_at,
    )


async def delete_candidate_note(
    db: AsyncSession,
    *,
    candidate_id: UUID,
    note_id: UUID,
    actor_id: UUID,
    is_admin: bool,
) -> Tuple[bool, Optional[str]]:
    res = await db.execute(
        select(CandidateNote).where(
            CandidateNote.id == note_id, CandidateNote.candidate_id == candidate_id
        )
    )
    note = res.scalar_one_or_none()
    if not note:
        return False, "not_found"
    if not is_admin and note.author_id != actor_id:
        return False, "forbidden"

    await db.delete(note)
    await record_audit(
        db,
        user_id=actor_id,
        action="delete",
        entity="candidate_note",
        entity_id=note_id,
        metadata={"candidate_id": str(candidate_id)},
        commit=False,
    )
    await db.commit()
    return True, None


# ---------------------------------------------------------------------------
# Audit Logs & Unified Candidate Activity Timeline
# ---------------------------------------------------------------------------

async def list_audit_logs(
    db: AsyncSession,
    *,
    entity: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[UUID] = None,
    limit: int = 100,
) -> List[AuditLogResponse]:
    stmt = select(AuditLog).options(selectinload(AuditLog.user))
    conditions = []
    if entity:
        conditions.append(AuditLog.entity == entity)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if action:
        conditions.append(AuditLog.action == action)
    if user_id:
        conditions.append(AuditLog.user_id == user_id)
    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        AuditLogResponse(
            id=r.id,
            user_id=r.user_id,
            user_name=(r.user.full_name or r.user.email) if r.user else None,
            user_email=r.user.email if r.user else None,
            action=r.action,
            entity=r.entity,
            entity_id=r.entity_id,
            metadata=r.details or {},
            timestamp=r.timestamp,
        )
        for r in rows
    ]


async def get_candidate_activity(
    db: AsyncSession,
    candidate_id: UUID,
    *,
    limit: int = 60,
) -> List[ActivityTimelineItem]:
    """Combine stage transition events, notes, and candidate audit logs chronologically."""
    items: List[ActivityTimelineItem] = []

    # 1. Application stage events for this candidate
    ev_res = await db.execute(
        select(ApplicationEvent)
        .join(Application, ApplicationEvent.application_id == Application.id)
        .options(
            selectinload(ApplicationEvent.actor),
            selectinload(ApplicationEvent.application).selectinload(Application.job),
        )
        .where(Application.candidate_id == candidate_id)
        .order_by(ApplicationEvent.created_at.desc())
        .limit(limit)
    )
    for ev in ev_res.scalars().all():
        job_title = ev.application.job.title if ev.application and ev.application.job else "Job"
        summary = (
            f"Moved from {ev.from_stage} to {ev.to_stage} for {job_title}"
            if ev.from_stage
            else f"Added to {job_title} ({ev.to_stage})"
        )
        if ev.reason:
            summary += f" — {ev.reason}"
        items.append(
            ActivityTimelineItem(
                id=f"ev-{ev.id}",
                kind="stage_change",
                action="stage_change",
                summary=summary,
                actor_name=(ev.actor.full_name or ev.actor.email) if ev.actor else None,
                actor_email=ev.actor.email if ev.actor else None,
                metadata={
                    "from_stage": ev.from_stage,
                    "to_stage": ev.to_stage,
                    "job_title": job_title,
                    "reason": ev.reason,
                },
                timestamp=ev.created_at,
            )
        )

    # 2. Notes
    notes = await list_candidate_notes(db, candidate_id)
    for n in notes[:limit]:
        items.append(
            ActivityTimelineItem(
                id=f"note-{n.id}",
                kind="note",
                action="note",
                summary=n.body,
                actor_name=n.author_name,
                actor_email=n.author_email,
                metadata={"tags": n.tags},
                timestamp=n.created_at,
            )
        )

    # 3. Sent / failed candidate emails (Phase 5.3)
    from app.models.workflow import EmailLog

    email_res = await db.execute(
        select(EmailLog)
        .options(selectinload(EmailLog.actor))
        .where(EmailLog.candidate_id == candidate_id)
        .order_by(EmailLog.created_at.desc())
        .limit(limit)
    )
    for em in email_res.scalars().all():
        items.append(
            ActivityTimelineItem(
                id=f"email-{em.id}",
                kind="email",
                action="email_sent",
                summary=f"Email ({em.status}): {em.subject}",
                actor_name=(em.actor.full_name or em.actor.email) if em.actor else None,
                actor_email=em.actor.email if em.actor else None,
                metadata={
                    "template_key": em.template_key,
                    "status": em.status,
                    "subject": em.subject,
                },
                timestamp=em.created_at,
            )
        )

    # 4. Direct candidate audit entries (view, edit, export)
    cid_str = str(candidate_id)
    aud_res = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(AuditLog.entity == "candidate", AuditLog.entity_id == cid_str)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    for a in aud_res.scalars().all():
        if a.action == "email_sent":
            continue  # Already shown as a dedicated `email` timeline entry above
        label_map = {
            "view": "Viewed candidate profile",
            "edit": "Updated candidate profile",
            "export": "Exported candidate profile or CV",
            "delete": "Deleted candidate profile",
            "create": "Created candidate profile",
            "brief_regenerate": "Regenerated candidate brief",
        }
        items.append(
            ActivityTimelineItem(
                id=f"audit-{a.id}",
                kind="audit",
                action=a.action,
                summary=label_map.get(a.action, f"{a.action} on candidate"),
                actor_name=(a.user.full_name or a.user.email) if a.user else None,
                actor_email=a.user.email if a.user else None,
                metadata=a.details or {},
                timestamp=a.timestamp,
            )
        )

    items.sort(key=lambda i: i.timestamp, reverse=True)
    return items[:limit]
