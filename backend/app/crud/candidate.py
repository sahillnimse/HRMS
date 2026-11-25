"""
Async CRUD operations for Candidates.

Handles normalized deduplication (email, phone_normalized, and pg_trgm fuzzy name),
resume file attachment status, creation, retrieval, listing with filters, stats,
and updates.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.candidate import Candidate, ResumeFile, ResumeFileStatus
from app.schemas.candidate import CandidateCreate, CandidateUpdate, DuplicateMatch
from app.services.file_storage import BaseStorage, storage as default_storage
from app.services.normalization import normalize_email, normalize_phone


async def get_candidate_by_email(db: AsyncSession, email: str) -> Optional[Candidate]:
    norm = normalize_email(email)
    if not norm:
        return None
    result = await db.execute(select(Candidate).where(func.lower(Candidate.email) == norm))
    return result.scalar_one_or_none()


async def get_candidate_by_phone(db: AsyncSession, phone: str) -> Optional[Candidate]:
    norm = normalize_phone(phone)
    if not norm:
        return None
    result = await db.execute(select(Candidate).where(Candidate.phone_normalized == norm))
    return result.scalar_one_or_none()


async def get_candidate_by_id(db: AsyncSession, candidate_id: str | UUID) -> Optional[Candidate]:
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    return result.scalar_one_or_none()


async def find_duplicates(
    db: AsyncSession,
    *,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    full_name: Optional[str] = None,
    exclude_id: Optional[UUID | str] = None,
    name_threshold: Optional[float] = None,
) -> List[DuplicateMatch]:
    """
    Return ALL potential duplicate candidates matching any of:
      - normalized email (lowercase + trimmed)
      - normalized phone (digits only, +91 / leading 0 stripped)
      - fuzzy full_name via pg_trgm similarity >= threshold
    """
    norm_email = normalize_email(email)
    norm_phone = normalize_phone(phone)
    clean_name = (full_name or "").strip()
    threshold = (
        settings.DUPLICATE_NAME_SIMILARITY_THRESHOLD
        if name_threshold is None
        else name_threshold
    )

    conditions = []
    if norm_email:
        conditions.append(func.lower(Candidate.email) == norm_email)
    if norm_phone:
        conditions.append(Candidate.phone_normalized == norm_phone)

    sim_expr = (
        func.similarity(Candidate.full_name, clean_name)
        if len(clean_name) >= 3
        else literal(0.0)
    )
    if len(clean_name) >= 3:
        conditions.append(sim_expr >= threshold)

    if not conditions:
        return []

    stmt = select(Candidate, sim_expr.label("name_sim")).where(or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(Candidate.id != exclude_id)

    result = await db.execute(stmt)
    rows = result.all()

    matches: List[DuplicateMatch] = []
    for cand, name_sim in rows:
        matched_fields: List[str] = []
        if norm_email and normalize_email(cand.email) == norm_email:
            matched_fields.append("email")
        if norm_phone and cand.phone_normalized == norm_phone:
            matched_fields.append("phone")
        sim_val = round(float(name_sim or 0.0), 3) if len(clean_name) >= 3 else None
        if sim_val is not None and sim_val >= threshold:
            matched_fields.append("name")

        if matched_fields:
            matches.append(
                DuplicateMatch(
                    candidate_id=cand.id,
                    full_name=cand.full_name,
                    email=cand.email,
                    phone=cand.phone,
                    primary_domain=cand.primary_domain,
                    matched_fields=matched_fields,
                    name_similarity=sim_val if "name" in matched_fields else None,
                )
            )

    # Sort strongest matches first (email/phone exact matches ahead of fuzzy-name-only)
    def _rank(m: DuplicateMatch) -> tuple[int, int, float]:
        exact_score = (2 if "email" in m.matched_fields else 0) + (
            2 if "phone" in m.matched_fields else 0
        )
        return (exact_score, len(m.matched_fields), m.name_similarity or 0.0)

    matches.sort(key=_rank, reverse=True)
    return matches


async def check_duplicate(
    db: AsyncSession,
    email: Optional[str],
    phone: Optional[str],
    full_name: Optional[str] = None,
) -> Optional[Candidate]:
    """Return the top duplicate Candidate if any exact email/phone match exists."""
    matches = await find_duplicates(db, email=email, phone=phone, full_name=full_name)
    if not matches:
        return None
    return await get_candidate_by_id(db, matches[0].candidate_id)


async def _mark_resume_attached(db: AsyncSession, resume_file_id: Optional[UUID]) -> None:
    if resume_file_id is None:
        return
    await db.execute(
        update(ResumeFile)
        .where(ResumeFile.id == resume_file_id)
        .values(status=ResumeFileStatus.attached.value)
    )


async def create_candidate(
    db: AsyncSession,
    candidate_in: CandidateCreate,
    *,
    is_duplicate_flagged: Optional[bool] = None,
) -> Candidate:
    norm_email = normalize_email(str(candidate_in.email) if candidate_in.email else None)
    norm_phone = normalize_phone(candidate_in.phone)
    flagged = (
        candidate_in.is_duplicate_flagged
        if is_duplicate_flagged is None
        else is_duplicate_flagged
    )

    db_obj = Candidate(
        full_name=candidate_in.full_name.strip(),
        email=norm_email,
        phone=candidate_in.phone.strip() if candidate_in.phone else None,
        phone_normalized=norm_phone,
        city=candidate_in.city,
        linkedin_url=candidate_in.linkedin_url,
        github_url=candidate_in.github_url,
        portfolio_url=candidate_in.portfolio_url,
        profile_summary=candidate_in.profile_summary,
        years_experience=candidate_in.years_experience,
        primary_domain=candidate_in.primary_domain,
        work_experience=candidate_in.work_experience,
        education=candidate_in.education,
        technical_skills=candidate_in.technical_skills,
        tools=candidate_in.tools,
        soft_skills=candidate_in.soft_skills,
        hobbies_interests=candidate_in.hobbies_interests,
        languages=candidate_in.languages,
        certifications=candidate_in.certifications,
        notice_period_days=candidate_in.notice_period_days,
        current_ctc=candidate_in.current_ctc,
        expected_ctc=candidate_in.expected_ctc,
        ctc_currency=candidate_in.ctc_currency.upper() if candidate_in.ctc_currency else None,
        preferred_locations=candidate_in.preferred_locations,
        open_to_relocate=candidate_in.open_to_relocate,
        raw_parsed_data=candidate_in.raw_parsed_data,
        resume_file_id=candidate_in.resume_file_id,
        is_duplicate_flagged=flagged,
    )
    db.add(db_obj)
    await _mark_resume_attached(db, candidate_in.resume_file_id)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def update_candidate(
    db: AsyncSession,
    db_obj: Candidate,
    candidate_in: CandidateUpdate,
) -> Candidate:
    update_data = candidate_in.model_dump(exclude_unset=True)

    if "full_name" in update_data and update_data["full_name"] is not None:
        update_data["full_name"] = update_data["full_name"].strip()
    if "email" in update_data:
        raw_email = update_data["email"]
        update_data["email"] = normalize_email(str(raw_email) if raw_email else None)
    if "phone" in update_data:
        raw_phone = update_data["phone"]
        update_data["phone"] = raw_phone.strip() if raw_phone else None
        update_data["phone_normalized"] = normalize_phone(update_data["phone"])
    if "ctc_currency" in update_data and update_data["ctc_currency"]:
        update_data["ctc_currency"] = update_data["ctc_currency"].strip().upper()

    new_resume_id = update_data.get("resume_file_id")
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    if new_resume_id is not None:
        await _mark_resume_attached(db, new_resume_id)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_candidates(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    primary_domain: Optional[str] = None,
    skills: Optional[str] = None,  # comma-separated
    min_years: Optional[float] = None,
    max_years: Optional[float] = None,
) -> Tuple[Sequence[Candidate], int]:
    """List candidates with pagination and filters."""
    stmt = select(Candidate)
    conditions = []

    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                Candidate.full_name.ilike(search_pattern),
                Candidate.email.ilike(search_pattern),
                Candidate.primary_domain.ilike(search_pattern),
            )
        )

    if primary_domain:
        conditions.append(Candidate.primary_domain == primary_domain)

    if skills:
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        for skill in skill_list:
            conditions.append(Candidate.technical_skills.contains([skill]))

    if min_years is not None:
        conditions.append(Candidate.years_experience >= min_years)

    if max_years is not None:
        conditions.append(Candidate.years_experience <= max_years)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    stmt = (
        stmt.options(selectinload(Candidate.resume_file))
        .order_by(Candidate.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    items = result.scalars().all()
    return items, total


async def get_candidate_stats(db: AsyncSession) -> dict:
    """Aggregate metrics for the dashboard: totals, averages, domains, top skills."""
    total = (await db.execute(select(func.count()).select_from(Candidate))).scalar_one()
    avg_years = (
        await db.execute(select(func.coalesce(func.avg(Candidate.years_experience), 0.0)))
    ).scalar_one()

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    added_this_week = (
        await db.execute(
            select(func.count()).select_from(Candidate).where(Candidate.created_at >= week_ago)
        )
    ).scalar_one()

    count_col = func.count().label("count")
    domain_rows = (
        await db.execute(
            select(Candidate.primary_domain, count_col)
            .group_by(Candidate.primary_domain)
            .order_by(count_col.desc(), Candidate.primary_domain)
            .limit(8)
        )
    ).all()

    skill_rows = (
        await db.execute(
            text(
                "SELECT skill, COUNT(*) AS count "
                "FROM candidates, jsonb_array_elements_text(technical_skills) AS skill "
                "GROUP BY skill ORDER BY count DESC, skill ASC LIMIT 15"
            )
        )
    ).all()

    return {
        "total": int(total),
        "avg_years_experience": round(float(avg_years or 0), 1),
        "added_this_week": int(added_this_week),
        "domains": [{"name": row[0], "count": int(row[1])} for row in domain_rows],
        "top_skills": [{"name": row[0], "count": int(row[1])} for row in skill_rows],
    }


async def delete_candidate(
    db: AsyncSession,
    candidate_id: str | UUID,
    *,
    storage_backend: Optional[BaseStorage] = None,
) -> bool:
    """
    Delete a candidate, its cascaded ResumeFile row, and the physical resume file
    from storage so no orphaned PII remains on disk or object storage.
    """
    result = await db.execute(
        select(Candidate)
        .options(selectinload(Candidate.resume_file))
        .where(Candidate.id == candidate_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False

    stored_filename: Optional[str] = None
    if obj.resume_file is not None:
        # Only delete physical file if no other candidate references the same ResumeFile
        other_refs = (
            await db.execute(
                select(func.count())
                .select_from(Candidate)
                .where(
                    Candidate.resume_file_id == obj.resume_file.id,
                    Candidate.id != obj.id,
                )
            )
        ).scalar_one()
        if other_refs == 0:
            stored_filename = obj.resume_file.stored_filename

    await db.delete(obj)
    await db.commit()

    if stored_filename:
        store = storage_backend or default_storage
        await store.delete_file(stored_filename)

    return True
