"""
Async CRUD operations for Candidates.

Handles deduplication (by email or phone), creation, retrieval, listing with
filters, and updates. All DB operations use the async SQLAlchemy session.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence, Tuple

from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.schemas.candidate import CandidateCreate, CandidateUpdate


async def get_candidate_by_email(db: AsyncSession, email: str) -> Optional[Candidate]:
    result = await db.execute(select(Candidate).where(Candidate.email == email))
    return result.scalar_one_or_none()


async def get_candidate_by_phone(db: AsyncSession, phone: str) -> Optional[Candidate]:
    result = await db.execute(select(Candidate).where(Candidate.phone == phone))
    return result.scalar_one_or_none()


async def get_candidate_by_id(db: AsyncSession, candidate_id: str) -> Optional[Candidate]:
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    return result.scalar_one_or_none()


async def check_duplicate(
    db: AsyncSession,
    email: Optional[str],
    phone: Optional[str],
) -> Optional[Candidate]:
    """
    Return an existing candidate if email OR phone matches.
    Used by the upload endpoint to flag duplicates before save.
    """
    conditions = []
    if email:
        conditions.append(Candidate.email == email)
    if phone:
        conditions.append(Candidate.phone == phone)

    if not conditions:
        return None

    result = await db.execute(select(Candidate).where(or_(*conditions)).limit(1))
    return result.scalar_one_or_none()


async def create_candidate(db: AsyncSession, candidate_in: CandidateCreate) -> Candidate:
    db_obj = Candidate(
        full_name=candidate_in.full_name,
        email=candidate_in.email,
        phone=candidate_in.phone,
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
        raw_parsed_data=candidate_in.raw_parsed_data,
        resume_file_id=candidate_in.resume_file_id,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def update_candidate(
    db: AsyncSession,
    db_obj: Candidate,
    candidate_in: CandidateUpdate,
) -> Candidate:
    update_data = candidate_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
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
    """
    List candidates with pagination and filters.

    Filters:
      - search: matches full_name, email, or primary_domain (ILIKE)
      - primary_domain: exact match
      - skills: any of the comma-separated skills present in technical_skills JSONB
      - min_years / max_years: years_experience range
    """
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

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Paginate + order
    offset = (page - 1) * page_size
    stmt = stmt.order_by(Candidate.created_at.desc()).offset(offset).limit(page_size)

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


async def delete_candidate(db: AsyncSession, candidate_id: str) -> bool:
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True
