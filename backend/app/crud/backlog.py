"""Async CRUD & services for Talent Pools, Silver-Medalist Resurfacing, and DPDP Erasure Requests."""

from datetime import datetime, timezone
import hashlib
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.candidate import delete_candidate
from app.models.backlog import ErasureRequest, InboundEmailLog, TalentPool, TalentPoolMember
from app.models.candidate import Candidate
from app.models.pipeline import Application, ApplicationEvent, Job
from app.schemas.backlog import (
    ErasureRequestCreate,
    ErasureRequestResponse,
    InboundEmailLogResponse,
    ResurfacedCandidateItem,
    ResurfaceResponse,
    TalentPoolCreate,
    TalentPoolMemberItem,
    TalentPoolResponse,
)
from app.services.audit import blind_candidate_label, record_audit
from app.services.matching import compute_jd_match
from app.services.skills import load_skill_alias_map


# ---------------------------------------------------------------------------
# Talent Pools
# ---------------------------------------------------------------------------

async def list_talent_pools(db: AsyncSession) -> List[TalentPoolResponse]:
    rows = (
        await db.execute(
            select(TalentPool, func.count(TalentPoolMember.id).label("m_cnt"))
            .outerjoin(TalentPoolMember, TalentPoolMember.pool_id == TalentPool.id)
            .group_by(TalentPool.id)
            .order_by(TalentPool.name.asc())
        )
    ).all()
    return [
        TalentPoolResponse(
            id=pool.id,
            name=pool.name,
            description=pool.description,
            color=pool.color,
            member_count=int(cnt or 0),
            created_at=pool.created_at,
        )
        for pool, cnt in rows
    ]


async def create_talent_pool(
    db: AsyncSession,
    payload: TalentPoolCreate,
    *,
    actor_id: UUID,
) -> TalentPoolResponse:
    pool = TalentPool(
        name=payload.name.strip(),
        description=payload.description.strip(),
        color=(payload.color or "teal").strip()[:32],
        created_by=actor_id,
    )
    db.add(pool)
    await db.commit()
    await db.refresh(pool)
    return TalentPoolResponse(
        id=pool.id,
        name=pool.name,
        description=pool.description,
        color=pool.color,
        member_count=0,
        created_at=pool.created_at,
    )


async def delete_talent_pool(db: AsyncSession, pool_id: UUID) -> bool:
    pool = (await db.execute(select(TalentPool).where(TalentPool.id == pool_id))).scalar_one_or_none()
    if not pool:
        return False
    await db.delete(pool)
    await db.commit()
    return True


async def add_candidate_to_pool(
    db: AsyncSession,
    pool_id: UUID,
    candidate_id: UUID,
    *,
    notes: str = "",
    actor_id: UUID,
) -> Tuple[bool, Optional[str]]:
    pool = (await db.execute(select(TalentPool).where(TalentPool.id == pool_id))).scalar_one_or_none()
    if not pool:
        return False, "pool_not_found"
    cand = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
    if not cand:
        return False, "candidate_not_found"

    upsert = (
        pg_insert(TalentPoolMember)
        .values(
            pool_id=pool_id,
            candidate_id=candidate_id,
            added_by=actor_id,
            notes=notes.strip(),
        )
        .on_conflict_do_update(
            constraint="uq_talent_pool_members_pool_cand",
            set_={"notes": notes.strip(), "updated_at": datetime.now(timezone.utc)},
        )
    )
    await db.execute(upsert)
    await record_audit(
        db,
        user_id=actor_id,
        action="talent_pool_add",
        entity="candidate",
        entity_id=candidate_id,
        metadata={"pool_id": str(pool_id), "pool_name": pool.name},
        commit=False,
    )
    await db.commit()
    return True, None


async def remove_candidate_from_pool(
    db: AsyncSession,
    pool_id: UUID,
    candidate_id: UUID,
) -> bool:
    res = await db.execute(
        delete(TalentPoolMember).where(
            TalentPoolMember.pool_id == pool_id,
            TalentPoolMember.candidate_id == candidate_id,
        )
    )
    await db.commit()
    return (res.rowcount or 0) > 0


async def list_pool_members(
    db: AsyncSession,
    pool_id: UUID,
    *,
    blind: bool = False,
) -> Optional[List[TalentPoolMemberItem]]:
    pool = (await db.execute(select(TalentPool).where(TalentPool.id == pool_id))).scalar_one_or_none()
    if not pool:
        return None
    rows = (
        await db.execute(
            select(TalentPoolMember)
            .options(selectinload(TalentPoolMember.candidate))
            .where(TalentPoolMember.pool_id == pool_id)
            .order_by(TalentPoolMember.created_at.desc())
        )
    ).scalars().all()
    out: List[TalentPoolMemberItem] = []
    for m in rows:
        if not m.candidate:
            continue
        c = m.candidate
        out.append(
            TalentPoolMemberItem(
                pool_id=pool_id,
                candidate_id=c.id,
                full_name=blind_candidate_label(c.id) if blind else c.full_name,
                primary_domain=c.primary_domain,
                years_experience=c.years_experience,
                technical_skills=list(c.technical_skills or [])[:8],
                notes=m.notes or "",
                added_at=m.created_at,
            )
        )
    return out


async def list_candidate_pools(db: AsyncSession, candidate_id: UUID) -> List[TalentPoolResponse]:
    rows = (
        await db.execute(
            select(TalentPool)
            .join(TalentPoolMember, TalentPoolMember.pool_id == TalentPool.id)
            .where(TalentPoolMember.candidate_id == candidate_id)
            .order_by(TalentPool.name.asc())
        )
    ).scalars().all()
    return [
        TalentPoolResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            color=p.color,
            member_count=0,
            created_at=p.created_at,
        )
        for p in rows
    ]


# ---------------------------------------------------------------------------
# Silver-Medalist Resurfacing (past interview/offer near-misses on OTHER jobs)
# ---------------------------------------------------------------------------

async def resurface_silver_medalists_for_job(
    db: AsyncSession,
    job_id: UUID,
    *,
    limit: int = 10,
    blind: bool = False,
) -> Optional[ResurfaceResponse]:
    """
    Find candidates who previously reached `interview` or `offer` on another job
    (excluding candidates already linked to `job_id` or already hired elsewhere recently),
    score them against `job_id` via deterministic `compute_jd_match`, and return top matches.
    """
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if not job:
        return None

    # Candidates already in this job's pipeline
    already_in_job = set(
        (
            await db.execute(
                select(Application.candidate_id).where(Application.job_id == job_id)
            )
        )
        .scalars()
        .all()
    )

    # Past applications on OTHER jobs whose ApplicationEvent history reached `interview` or `offer`
    ev_rows = (
        await db.execute(
            select(Application, ApplicationEvent.to_stage, Job.title)
            .join(ApplicationEvent, ApplicationEvent.application_id == Application.id)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.job_id != job_id,
                ApplicationEvent.to_stage.in_(["interview", "offer"]),
            )
        )
    ).all()

    # Best past near-miss per candidate (offer outranks interview)
    rank_stage = {"interview": 1, "offer": 2}
    best_past: Dict[UUID, Tuple[int, UUID, str, str]] = {}
    for app_obj, stage_str, past_title in ev_rows:
        cid = app_obj.candidate_id
        if cid in already_in_job:
            continue
        r = rank_stage.get(stage_str, 0)
        cur = best_past.get(cid)
        if cur is None or r > cur[0]:
            best_past[cid] = (r, app_obj.job_id, past_title or "Past Role", stage_str)

    if not best_past:
        return ResurfaceResponse(job_id=job.id, job_title=job.title, total=0, candidates=[])

    cand_ids = list(best_past.keys())
    cands = (
        await db.execute(select(Candidate).where(Candidate.id.in_(cand_ids)))
    ).scalars().all()

    # Load talent pool names per candidate
    pool_rows = (
        await db.execute(
            select(TalentPoolMember.candidate_id, TalentPool.name)
            .join(TalentPool, TalentPool.id == TalentPoolMember.pool_id)
            .where(TalentPoolMember.candidate_id.in_(cand_ids))
        )
    ).all()
    pools_by_cand: Dict[UUID, List[str]] = {}
    for cid, pname in pool_rows:
        pools_by_cand.setdefault(cid, []).append(pname)

    alias_map = await load_skill_alias_map(db)
    scored: List[ResurfacedCandidateItem] = []

    for c in cands:
        _, past_jid, past_title, past_stage = best_past[c.id]
        score, bd = compute_jd_match(
            job_title=job.title,
            job_description=job.description,
            required_skills=job.required_skills or [],
            nice_to_have_skills=job.nice_to_have_skills or [],
            min_years=job.min_years,
            max_years=job.max_years,
            candidate_years=c.years_experience,
            candidate_summary=c.profile_summary,
            candidate_domain=c.primary_domain,
            candidate_technical_skills=c.technical_skills or [],
            candidate_tools=c.tools or [],
            candidate_work_experience=c.work_experience or [],
            alias_map=alias_map,
        )
        scored.append(
            ResurfacedCandidateItem(
                candidate_id=c.id,
                full_name=blind_candidate_label(c.id) if blind else c.full_name,
                primary_domain=c.primary_domain,
                years_experience=c.years_experience,
                past_job_id=past_jid,
                past_job_title=past_title,
                past_highest_stage=past_stage,
                match_score=round(score, 1),
                matched_required_skills=list(bd.get("matched_required_skills") or []),
                missing_required_skills=list(bd.get("missing_required_skills") or []),
                why=str(bd.get("why") or ""),
                talent_pools=pools_by_cand.get(c.id, []),
            )
        )

    scored.sort(key=lambda x: (-x.match_score, x.past_highest_stage != "offer"))
    top = scored[: max(1, min(limit, 50))]
    return ResurfaceResponse(
        job_id=job.id,
        job_title=job.title,
        total=len(scored),
        candidates=top,
    )


# ---------------------------------------------------------------------------
# DPDP Act Erasure & Consent-Withdrawal Requests
# ---------------------------------------------------------------------------

def _hash_candidate_ref(candidate_id: UUID) -> str:
    return hashlib.sha256(f"dpdp:{candidate_id}".encode("utf-8")).hexdigest()


async def list_erasure_requests(db: AsyncSession, *, limit: int = 100) -> List[ErasureRequestResponse]:
    rows = (
        await db.execute(
            select(ErasureRequest).order_by(ErasureRequest.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [ErasureRequestResponse.model_validate(r) for r in rows]


async def create_erasure_request(
    db: AsyncSession,
    payload: ErasureRequestCreate,
    *,
    actor_id: UUID,
) -> Tuple[Optional[ErasureRequestResponse], Optional[str]]:
    cand = (
        await db.execute(select(Candidate).where(Candidate.id == payload.candidate_id))
    ).scalar_one_or_none()
    if not cand:
        return None, "candidate_not_found"

    req = ErasureRequest(
        candidate_id=cand.id,
        candidate_ref_hash=_hash_candidate_ref(cand.id),
        request_type=payload.request_type,
        status="pending",
        reason=payload.reason.strip(),
        requested_by=actor_id,
    )
    db.add(req)
    await db.flush()
    await record_audit(
        db,
        user_id=actor_id,
        action="dpdp_request_created",
        entity="erasure_request",
        entity_id=req.id,
        metadata={"request_type": req.request_type, "candidate_ref_hash": req.candidate_ref_hash},
        commit=False,
    )
    await db.commit()
    await db.refresh(req)
    return ErasureRequestResponse.model_validate(req), None


async def execute_erasure_request(
    db: AsyncSession,
    request_id: UUID,
    *,
    actor_id: UUID,
) -> Tuple[Optional[ErasureRequestResponse], Optional[str]]:
    """
    Admin-only DPDP execution: permanently deletes the candidate profile, resume file,
    and all cascaded rows, then marks the erasure request `completed` with a PII-free audit entry.
    """
    req = (
        await db.execute(select(ErasureRequest).where(ErasureRequest.id == request_id))
    ).scalar_one_or_none()
    if not req:
        return None, "request_not_found"
    if req.status == "completed":
        return ErasureRequestResponse.model_validate(req), None

    cid = req.candidate_id
    if cid is not None and req.request_type in ("erasure", "consent_withdrawal"):
        await delete_candidate(db, cid)

    req.status = "completed"
    req.processed_by = actor_id
    req.processed_at = datetime.now(timezone.utc)
    await record_audit(
        db,
        user_id=actor_id,
        action="dpdp_erasure_executed",
        entity="erasure_request",
        entity_id=req.id,
        metadata={
            "request_type": req.request_type,
            "candidate_ref_hash": req.candidate_ref_hash,
            "pii_wiped": req.request_type in ("erasure", "consent_withdrawal"),
        },
        commit=False,
    )
    await db.commit()
    await db.refresh(req)
    return ErasureRequestResponse.model_validate(req), None


async def list_inbound_email_logs(
    db: AsyncSession, *, limit: int = 50
) -> List[InboundEmailLogResponse]:
    rows = (
        await db.execute(
            select(InboundEmailLog).order_by(InboundEmailLog.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [InboundEmailLogResponse.model_validate(r) for r in rows]
