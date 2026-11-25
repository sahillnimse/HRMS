"""Async CRUD for skill normalizations and cached JD match scoring."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.candidate import Candidate
from app.models.matching import JobMatch, SkillNormalization
from app.models.pipeline import Application, Job
from app.schemas.matching import (
    JobMatchCandidateSummary,
    JobMatchItem,
    SkillNormalizationCreate,
)
from app.services.embeddings import build_job_embedding_text, generate_embedding
from app.services.matching import compute_jd_match, generate_match_explanation
from app.services.skills import load_skill_alias_map


async def list_skill_normalizations(db: AsyncSession) -> Sequence[SkillNormalization]:
    res = await db.execute(
        select(SkillNormalization).order_by(SkillNormalization.canonical_name.asc())
    )
    return res.scalars().all()


async def upsert_skill_normalization(
    db: AsyncSession,
    payload: SkillNormalizationCreate,
) -> SkillNormalization:
    canonical = payload.canonical_name.strip()
    clean_aliases = []
    seen = {canonical.lower()}
    for a in payload.aliases:
        s = a.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            clean_aliases.append(s)

    existing = (
        await db.execute(
            select(SkillNormalization).where(SkillNormalization.canonical_name == canonical)
        )
    ).scalar_one_or_none()
    if existing:
        existing.aliases = clean_aliases
        await db.commit()
        await db.refresh(existing)
        return existing

    row = SkillNormalization(canonical_name=canonical, aliases=clean_aliases)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _application_stage_map(db: AsyncSession, job_id: UUID) -> Dict[UUID, str]:
    rows = (
        await db.execute(
            select(Application.candidate_id, Application.stage).where(Application.job_id == job_id)
        )
    ).all()
    return {cid: stage.value for cid, stage in rows}


async def run_job_matching(
    db: AsyncSession,
    job: Job,
    *,
    candidate_ids: Optional[List[UUID]] = None,
    include_explanations: bool = True,
) -> List[JobMatchItem]:
    """
    Deterministically score candidates against a Job, generate optional LLM explanations
    solely from the structured breakdown, upsert into `job_matches`, and return ranked items.
    """
    alias_map = await load_skill_alias_map(db)

    stmt = select(Candidate)
    if candidate_ids:
        stmt = stmt.where(Candidate.id.in_(candidate_ids))
    candidates = list((await db.execute(stmt)).scalars().all())
    if not candidates:
        return []

    job_emb = await generate_embedding(
        build_job_embedding_text(
            title=job.title,
            department=job.department,
            description=job.description,
            required_skills=job.required_skills or [],
            nice_to_have_skills=job.nice_to_have_skills or [],
        )
    )

    now = datetime.now(timezone.utc)
    for cand in candidates:
        score, breakdown = compute_jd_match(
            job_title=job.title,
            job_description=job.description,
            required_skills=job.required_skills or [],
            nice_to_have_skills=job.nice_to_have_skills or [],
            min_years=job.min_years,
            max_years=job.max_years,
            candidate_years=cand.years_experience,
            candidate_summary=cand.profile_summary,
            candidate_domain=cand.primary_domain,
            candidate_technical_skills=cand.technical_skills or [],
            candidate_tools=cand.tools or [],
            candidate_work_experience=cand.work_experience or [],
            alias_map=alias_map,
            job_embedding=job_emb,
            candidate_embedding=cand.embedding_json,
        )
        explanation, model_ver = await generate_match_explanation(
            job_title=job.title,
            score=score,
            breakdown=breakdown,
            candidate_summary=cand.profile_summary,
            use_llm=include_explanations,
        )

        upsert_stmt = (
            pg_insert(JobMatch)
            .values(
                job_id=job.id,
                candidate_id=cand.id,
                score=score,
                breakdown=breakdown,
                explanation=explanation,
                model_version=model_ver,
                computed_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_job_matches_job_candidate",
                set_={
                    "score": score,
                    "breakdown": breakdown,
                    "explanation": explanation,
                    "model_version": model_ver,
                    "computed_at": now,
                    "updated_at": now,
                },
            )
        )
        await db.execute(upsert_stmt)

    await db.commit()
    return await list_job_matches(db, job.id, candidate_ids=candidate_ids)


async def list_job_matches(
    db: AsyncSession,
    job_id: UUID,
    *,
    candidate_ids: Optional[List[UUID]] = None,
) -> List[JobMatchItem]:
    """Return cached ranked matches for a job."""
    stmt = (
        select(JobMatch)
        .options(selectinload(JobMatch.candidate))
        .where(JobMatch.job_id == job_id)
    )
    if candidate_ids:
        stmt = stmt.where(JobMatch.candidate_id.in_(candidate_ids))
    stmt = stmt.order_by(JobMatch.score.desc(), JobMatch.computed_at.desc())

    rows = (await db.execute(stmt)).scalars().all()
    stage_map = await _application_stage_map(db, job_id)

    items: List[JobMatchItem] = []
    for row in rows:
        stage = stage_map.get(row.candidate_id)
        items.append(
            JobMatchItem(
                id=row.id,
                job_id=row.job_id,
                candidate_id=row.candidate_id,
                score=row.score,
                breakdown=row.breakdown or {},
                explanation=row.explanation,
                model_version=row.model_version,
                computed_at=row.computed_at,
                in_pipeline=stage is not None,
                application_stage=stage,
                candidate=(
                    JobMatchCandidateSummary.model_validate(row.candidate)
                    if row.candidate is not None
                    else None
                ),
            )
        )
    return items
