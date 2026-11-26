"""
Phase 6 Analytics service derived strictly from existing ApplicationEvent history,
Application, Job, and Candidate.source (added in migration 0006).

No duplicate analytics tables are stored.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.candidate import Candidate
from app.models.pipeline import Application, ApplicationEvent, ApplicationStage, Job
from app.schemas.analytics import (
    FunnelAnalyticsResponse,
    FunnelStageMetric,
    SourceMetric,
    SourcesAnalyticsResponse,
    StuckCandidateItem,
    StuckCandidatesResponse,
    TimeInStageMetric,
    TimeInStageResponse,
    TimeToHireResponse,
)
from app.services.audit import blind_candidate_label

FUNNEL_STAGES: Tuple[str, ...] = ("applied", "screened", "interview", "offer", "hired")
ACTIVE_STAGES: Tuple[str, ...] = ("applied", "screened", "interview", "offer")


def _date_bounds(
    start_date: Optional[date],
    end_date: Optional[date],
) -> Tuple[Optional[datetime], Optional[datetime]]:
    start_dt = (
        datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
        if start_date is not None
        else None
    )
    end_dt_exclusive = (
        datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc)
        + timedelta(days=1)
        if end_date is not None
        else None
    )
    return start_dt, end_dt_exclusive


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _round1(val: float) -> float:
    return round(val, 1)


async def _load_applications_and_events(
    db: AsyncSession,
    *,
    job_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Tuple[List[Application], Dict[UUID, List[ApplicationEvent]]]:
    start_dt, end_dt = _date_bounds(start_date, end_date)
    app_stmt = select(Application)
    if job_id is not None:
        app_stmt = app_stmt.where(Application.job_id == job_id)
    if start_dt is not None:
        app_stmt = app_stmt.where(Application.created_at >= start_dt)
    if end_dt is not None:
        app_stmt = app_stmt.where(Application.created_at < end_dt)

    apps = list((await db.execute(app_stmt)).scalars().all())
    if not apps:
        return [], {}

    app_ids = [a.id for a in apps]
    ev_stmt = (
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id.in_(app_ids))
        .order_by(ApplicationEvent.application_id, ApplicationEvent.created_at.asc(), ApplicationEvent.id.asc())
    )
    events = list((await db.execute(ev_stmt)).scalars().all())
    events_by_app: Dict[UUID, List[ApplicationEvent]] = defaultdict(list)
    for ev in events:
        events_by_app[ev.application_id].append(ev)
    return apps, events_by_app


async def get_funnel_analytics(
    db: AsyncSession,
    *,
    job_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> FunnelAnalyticsResponse:
    """Compute stage reach, current counts, and step-by-step funnel conversion rates."""
    apps, events_by_app = await _load_applications_and_events(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )

    reached_counts: Dict[str, int] = {stage: 0 for stage in FUNNEL_STAGES}
    current_counts: Dict[str, int] = {stage: 0 for stage in FUNNEL_STAGES}
    rejected_count = 0
    active_count = 0

    for app in apps:
        cur_stage = app.stage.value if isinstance(app.stage, ApplicationStage) else str(app.stage)
        if cur_stage in current_counts:
            current_counts[cur_stage] += 1
        if cur_stage == ApplicationStage.rejected.value:
            rejected_count += 1
        elif cur_stage != ApplicationStage.hired.value:
            active_count += 1

        reached = {"applied", cur_stage}
        for ev in events_by_app.get(app.id, []):
            if ev.to_stage:
                reached.add(ev.to_stage)
            if ev.from_stage:
                reached.add(ev.from_stage)

        for stage in FUNNEL_STAGES:
            if stage in reached:
                reached_counts[stage] += 1

    total = len(apps)
    applied_reached = reached_counts["applied"]
    hired_count = reached_counts["hired"]

    metrics: List[FunnelStageMetric] = []
    prev_reached: Optional[int] = None
    for stage in FUNNEL_STAGES:
        reached_n = reached_counts[stage]
        conv_prev: Optional[float] = None
        if prev_reached is not None:
            conv_prev = _round1((reached_n / prev_reached) * 100.0) if prev_reached > 0 else 0.0
        conv_applied = (
            _round1((reached_n / applied_reached) * 100.0) if applied_reached > 0 else 0.0
        )
        metrics.append(
            FunnelStageMetric(
                stage=stage,
                reached_count=reached_n,
                current_count=current_counts[stage],
                conversion_from_previous_pct=conv_prev,
                conversion_from_applied_pct=conv_applied,
            )
        )
        prev_reached = reached_n

    overall_hire_rate = _round1((hired_count / total) * 100.0) if total > 0 else 0.0
    return FunnelAnalyticsResponse(
        total_applications=total,
        active_applications=active_count,
        hired_count=hired_count,
        rejected_count=rejected_count,
        overall_hire_rate_pct=overall_hire_rate,
        stages=metrics,
    )


async def get_time_in_stage_analytics(
    db: AsyncSession,
    *,
    job_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> TimeInStageResponse:
    """
    Compute average, median, min, and max days spent in each active pipeline stage,
    derived from consecutive ApplicationEvent transition timestamps.
    """
    apps, events_by_app = await _load_applications_and_events(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )

    durations: Dict[str, List[float]] = {stage: [] for stage in ACTIVE_STAGES}
    for app in apps:
        evs = events_by_app.get(app.id, [])
        if len(evs) < 2:
            continue
        for idx in range(len(evs) - 1):
            cur_ev = evs[idx]
            nxt_ev = evs[idx + 1]
            stage_key = cur_ev.to_stage
            if stage_key not in durations:
                continue
            delta_sec = (_ensure_utc(nxt_ev.created_at) - _ensure_utc(cur_ev.created_at)).total_seconds()
            if delta_sec >= 0:
                durations[stage_key].append(delta_sec / 86400.0)

    items: List[TimeInStageMetric] = []
    for stage in ACTIVE_STAGES:
        samples = durations[stage]
        if samples:
            items.append(
                TimeInStageMetric(
                    stage=stage,
                    avg_days=_round1(sum(samples) / len(samples)),
                    median_days=_round1(float(median(samples))),
                    min_days=_round1(min(samples)),
                    max_days=_round1(max(samples)),
                    sample_count=len(samples),
                )
            )
        else:
            items.append(TimeInStageMetric(stage=stage, sample_count=0))

    return TimeInStageResponse(stages=items)


async def get_time_to_hire_analytics(
    db: AsyncSession,
    *,
    job_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> TimeToHireResponse:
    """
    Compute elapsed days from initial ApplicationEvent (or Application.created_at)
    to the first `hired` ApplicationEvent for hired applications.
    """
    apps, events_by_app = await _load_applications_and_events(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )

    days_list: List[float] = []
    for app in apps:
        evs = events_by_app.get(app.id, [])
        hired_ev = next((e for e in evs if e.to_stage == ApplicationStage.hired.value), None)
        if hired_ev is None:
            continue
        start_ts = _ensure_utc(evs[0].created_at) if evs else _ensure_utc(app.created_at)
        end_ts = _ensure_utc(hired_ev.created_at)
        delta_days = max(0.0, (end_ts - start_ts).total_seconds() / 86400.0)
        days_list.append(delta_days)

    if not days_list:
        return TimeToHireResponse(hired_count=0)

    return TimeToHireResponse(
        hired_count=len(days_list),
        avg_days=_round1(sum(days_list) / len(days_list)),
        median_days=_round1(float(median(days_list))),
        min_days=_round1(min(days_list)),
        max_days=_round1(max(days_list)),
    )


async def get_source_analytics(
    db: AsyncSession,
    *,
    job_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> SourcesAnalyticsResponse:
    """
    Aggregate candidate volume, application funnel progress, and hire rates
    by `Candidate.source` (added in migration 0006).
    """
    start_dt, end_dt = _date_bounds(start_date, end_date)
    apps, events_by_app = await _load_applications_and_events(
        db, job_id=job_id, start_date=start_date, end_date=end_date
    )

    cand_sources: Dict[UUID, str] = {}
    if job_id is not None:
        cand_ids = list({a.candidate_id for a in apps})
        if cand_ids:
            c_rows = (
                await db.execute(select(Candidate.id, Candidate.source).where(Candidate.id.in_(cand_ids)))
            ).all()
            for cid, src in c_rows:
                cand_sources[cid] = (src or "unknown").strip() or "unknown"
    else:
        c_stmt = select(Candidate.id, Candidate.source)
        if start_dt is not None:
            c_stmt = c_stmt.where(Candidate.created_at >= start_dt)
        if end_dt is not None:
            c_stmt = c_stmt.where(Candidate.created_at < end_dt)
        c_rows = (await db.execute(c_stmt)).all()
        for cid, src in c_rows:
            cand_sources[cid] = (src or "unknown").strip() or "unknown"

        # Ensure candidates who applied in the date window are also resolved
        missing_cids = list({a.candidate_id for a in apps if a.candidate_id not in cand_sources})
        if missing_cids:
            extra_rows = (
                await db.execute(
                    select(Candidate.id, Candidate.source).where(Candidate.id.in_(missing_cids))
                )
            ).all()
            for cid, src in extra_rows:
                cand_sources[cid] = (src or "unknown").strip() or "unknown"

    cands_per_source: Dict[str, set[UUID]] = defaultdict(set)
    for cid, src in cand_sources.items():
        cands_per_source[src].add(cid)

    apps_count: Dict[str, int] = defaultdict(int)
    screened_count: Dict[str, int] = defaultdict(int)
    interview_count: Dict[str, int] = defaultdict(int)
    hired_count: Dict[str, int] = defaultdict(int)

    for app in apps:
        src = cand_sources.get(app.candidate_id, "unknown")
        cands_per_source[src].add(app.candidate_id)
        apps_count[src] += 1

        cur_stage = app.stage.value if isinstance(app.stage, ApplicationStage) else str(app.stage)
        reached = {cur_stage}
        for ev in events_by_app.get(app.id, []):
            if ev.to_stage:
                reached.add(ev.to_stage)
            if ev.from_stage:
                reached.add(ev.from_stage)

        if "screened" in reached:
            screened_count[src] += 1
        if "interview" in reached:
            interview_count[src] += 1
        if "hired" in reached:
            hired_count[src] += 1

    all_sources = set(cands_per_source.keys()) | set(apps_count.keys())
    items: List[SourceMetric] = []
    for src in all_sources:
        a_cnt = apps_count[src]
        h_cnt = hired_count[src]
        hire_rate = _round1((h_cnt / a_cnt) * 100.0) if a_cnt > 0 else 0.0
        items.append(
            SourceMetric(
                source=src,
                candidates_count=len(cands_per_source[src]),
                applications_count=a_cnt,
                screened_count=screened_count[src],
                interview_count=interview_count[src],
                hired_count=h_cnt,
                hire_rate_pct=hire_rate,
            )
        )

    items.sort(key=lambda x: (-x.applications_count, -x.candidates_count, x.source))
    return SourcesAnalyticsResponse(
        total_candidates=sum(i.candidates_count for i in items),
        sources=items,
    )


async def get_stuck_applications(
    db: AsyncSession,
    *,
    job_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    thresholds_override: Optional[Dict[str, int]] = None,
    blind: bool = False,
) -> StuckCandidatesResponse:
    """
    Return active applications (applied/screened/interview/offer) that have remained
    in their current stage for at least `threshold_days` days, derived from the latest
    matching ApplicationEvent timestamp (falling back to Application.stage_changed_at).
    """
    thresholds: Dict[str, int] = {
        "applied": settings.STUCK_APPLIED_DAYS,
        "screened": settings.STUCK_SCREENED_DAYS,
        "interview": settings.STUCK_INTERVIEW_DAYS,
        "offer": settings.STUCK_OFFER_DAYS,
    }
    if thresholds_override:
        for k, v in thresholds_override.items():
            if k in thresholds and v is not None:
                thresholds[k] = v

    start_dt, end_dt = _date_bounds(start_date, end_date)
    active_enums = [
        ApplicationStage.applied,
        ApplicationStage.screened,
        ApplicationStage.interview,
        ApplicationStage.offer,
    ]
    stmt = (
        select(Application, Candidate.full_name, Job.title)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Job, Job.id == Application.job_id)
        .where(Application.stage.in_(active_enums))
    )
    if job_id is not None:
        stmt = stmt.where(Application.job_id == job_id)
    if start_dt is not None:
        stmt = stmt.where(Application.created_at >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(Application.created_at < end_dt)

    rows = (await db.execute(stmt)).all()
    if not rows:
        return StuckCandidatesResponse(thresholds=thresholds, total_stuck=0, items=[])

    app_ids = [r[0].id for r in rows]
    ev_stmt = (
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id.in_(app_ids))
        .order_by(ApplicationEvent.created_at.desc(), ApplicationEvent.id.desc())
    )
    events = list((await db.execute(ev_stmt)).scalars().all())
    latest_stage_entry: Dict[Tuple[UUID, str], datetime] = {}
    for ev in events:
        key = (ev.application_id, ev.to_stage)
        if key not in latest_stage_entry:
            latest_stage_entry[key] = _ensure_utc(ev.created_at)

    now = datetime.now(timezone.utc)
    items: List[StuckCandidateItem] = []
    for app, candidate_name, job_title in rows:
        stage_str = app.stage.value if isinstance(app.stage, ApplicationStage) else str(app.stage)
        threshold = thresholds.get(stage_str, 7)
        entered_at = latest_stage_entry.get((app.id, stage_str)) or _ensure_utc(app.stage_changed_at)
        days_in_stage = max(0.0, (now - entered_at).total_seconds() / 86400.0)
        if days_in_stage >= float(threshold):
            display_name = (
                blind_candidate_label(app.candidate_id)
                if blind
                else (candidate_name or "Unknown Candidate")
            )
            items.append(
                StuckCandidateItem(
                    application_id=app.id,
                    candidate_id=app.candidate_id,
                    candidate_name=display_name,
                    job_id=app.job_id,
                    job_title=job_title or "Untitled Job",
                    stage=stage_str,
                    days_in_stage=_round1(days_in_stage),
                    threshold_days=threshold,
                    stage_changed_at=entered_at,
                )
            )

    items.sort(key=lambda x: (-x.days_in_stage, x.stage_changed_at))
    return StuckCandidatesResponse(
        thresholds=thresholds,
        total_stuck=len(items),
        items=items,
    )
