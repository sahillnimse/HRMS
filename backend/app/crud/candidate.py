"""
Async CRUD operations for Candidates.

Handles normalized deduplication (email, phone_normalized, and pg_trgm fuzzy name),
skill normalization on save and filter, case-insensitive skill/tool filtering,
tsvector + pgvector/embedding updates, hybrid search, stats, and file cleanup.
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
from app.schemas.matching import CandidateSearchItem, CandidateSearchResponse
from app.services.embeddings import (
    build_candidate_embedding_text,
    cosine_similarity,
    generate_embedding,
    has_pgvector_column,
    sync_candidate_pgvector,
)
from app.services.file_storage import BaseStorage, storage as default_storage
from app.services.normalization import normalize_email, normalize_phone
from app.services.skills import load_skill_alias_map, normalize_skill_list


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


async def _refresh_search_vector(db: AsyncSession, candidate_id: UUID) -> None:
    """Recompute weighted tsvector over name, domain, work titles, skills/tools, and summary."""
    await db.execute(
        text(
            """
            UPDATE candidates
            SET search_vector =
                setweight(to_tsvector('english', COALESCE(full_name, '') || ' ' || COALESCE(primary_domain, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE((
                    SELECT string_agg(elem->>'job_title', ' ')
                    FROM jsonb_array_elements(COALESCE(work_experience, '[]'::jsonb)) AS elem
                ), '')), 'A') ||
                setweight(to_tsvector('english', COALESCE((
                    SELECT string_agg(val, ' ')
                    FROM jsonb_array_elements_text(COALESCE(technical_skills, '[]'::jsonb) || COALESCE(tools, '[]'::jsonb)) AS val
                ), '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(profile_summary, '')), 'C')
            WHERE id = :cid
            """
        ),
        {"cid": candidate_id},
    )


async def create_candidate(
    db: AsyncSession,
    candidate_in: CandidateCreate,
    *,
    is_duplicate_flagged: Optional[bool] = None,
) -> Candidate:
    alias_map = await load_skill_alias_map(db)
    norm_tech = normalize_skill_list(candidate_in.technical_skills, alias_map)
    norm_tools = normalize_skill_list(candidate_in.tools, alias_map)

    norm_email = normalize_email(str(candidate_in.email) if candidate_in.email else None)
    norm_phone = normalize_phone(candidate_in.phone)
    flagged = (
        candidate_in.is_duplicate_flagged
        if is_duplicate_flagged is None
        else is_duplicate_flagged
    )

    emb_text = build_candidate_embedding_text(
        primary_domain=candidate_in.primary_domain,
        profile_summary=candidate_in.profile_summary,
        technical_skills=norm_tech,
        tools=norm_tools,
        work_experience=candidate_in.work_experience,
    )
    emb_vec = await generate_embedding(emb_text)

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
        technical_skills=norm_tech,
        tools=norm_tools,
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
        consent_given_at=candidate_in.consent_given_at,
        source=(candidate_in.source or "upload").strip()[:80] or "upload",
        raw_parsed_data=candidate_in.raw_parsed_data,
        embedding_json=emb_vec,
        resume_file_id=candidate_in.resume_file_id,
        is_duplicate_flagged=flagged,
    )
    db.add(db_obj)
    await db.flush()
    await _mark_resume_attached(db, candidate_in.resume_file_id)
    await _refresh_search_vector(db, db_obj.id)
    if emb_vec:
        await sync_candidate_pgvector(db, db_obj.id, emb_vec)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def update_candidate(
    db: AsyncSession,
    db_obj: Candidate,
    candidate_in: CandidateUpdate,
) -> Candidate:
    update_data = candidate_in.model_dump(exclude_unset=True)
    alias_map = (
        await load_skill_alias_map(db)
        if ("technical_skills" in update_data or "tools" in update_data)
        else {}
    )

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
    if "technical_skills" in update_data and update_data["technical_skills"] is not None:
        update_data["technical_skills"] = normalize_skill_list(
            update_data["technical_skills"], alias_map
        )
    if "tools" in update_data and update_data["tools"] is not None:
        update_data["tools"] = normalize_skill_list(update_data["tools"], alias_map)

    if "raw_parsed_data" in update_data and isinstance(update_data["raw_parsed_data"], dict):
        # Preserve server-side _resume_text stored in DB even though API responses strip it
        existing_resume_text = (db_obj.raw_parsed_data or {}).get("_resume_text")
        if existing_resume_text and "_resume_text" not in update_data["raw_parsed_data"]:
            update_data["raw_parsed_data"] = {
                **update_data["raw_parsed_data"],
                "_resume_text": existing_resume_text,
            }

    new_resume_id = update_data.get("resume_file_id")
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    if new_resume_id is not None:
        await _mark_resume_attached(db, new_resume_id)

    search_relevant_fields = {
        "full_name",
        "primary_domain",
        "profile_summary",
        "technical_skills",
        "tools",
        "work_experience",
    }
    if search_relevant_fields & set(update_data.keys()):
        await db.flush()
        await _refresh_search_vector(db, db_obj.id)
        emb_text = build_candidate_embedding_text(
            primary_domain=db_obj.primary_domain,
            profile_summary=db_obj.profile_summary,
            technical_skills=db_obj.technical_skills,
            tools=db_obj.tools,
            work_experience=db_obj.work_experience,
        )
        emb_vec = await generate_embedding(emb_text)
        if emb_vec is not None:
            db_obj.embedding_json = emb_vec
            await sync_candidate_pgvector(db, db_obj.id, emb_vec)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


def _skill_filter_condition(skill_canonical: str, param_name: str):
    """Case-insensitive match across BOTH technical_skills AND tools JSONB arrays."""
    return text(
        "EXISTS ("
        "  SELECT 1 FROM jsonb_array_elements_text("
        "    COALESCE(candidates.technical_skills, '[]'::jsonb) || "
        "    COALESCE(candidates.tools, '[]'::jsonb)"
        "  ) AS _sk "
        f"  WHERE LOWER(_sk) = LOWER(:{param_name})"
        ")"
    ).bindparams(**{param_name: skill_canonical})


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
    """List candidates with pagination and normalized case-insensitive skill/tool filters."""
    stmt = select(Candidate)
    conditions = []

    if search:
        search_pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                Candidate.full_name.ilike(search_pattern),
                Candidate.email.ilike(search_pattern),
                Candidate.primary_domain.ilike(search_pattern),
                Candidate.search_vector.op("@@")(func.plainto_tsquery("english", search.strip())),
            )
        )

    if primary_domain:
        conditions.append(func.lower(Candidate.primary_domain) == primary_domain.strip().lower())

    if skills:
        alias_map = await load_skill_alias_map(db)
        raw_skills = [s.strip() for s in skills.split(",") if s.strip()]
        norm_skills = normalize_skill_list(raw_skills, alias_map)
        for idx, skill in enumerate(norm_skills):
            conditions.append(_skill_filter_condition(skill, f"sk_{idx}"))

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


async def search_candidates_hybrid(
    db: AsyncSession,
    *,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    primary_domain: Optional[str] = None,
    skills: Optional[str] = None,
    min_years: Optional[float] = None,
    max_years: Optional[float] = None,
) -> CandidateSearchResponse:
    """
    Hybrid search combining PostgreSQL FTS (`search_vector`), `pg_trgm` fuzzy similarity,
    normalized case-insensitive skill/tool matching, and optional Gemini semantic similarity
    (behind `ENABLE_SEMANTIC_SEARCH`).
    """
    query_text = (q or "").strip()
    alias_map = await load_skill_alias_map(db)

    norm_filter_skills: List[str] = []
    conditions = []
    if primary_domain:
        conditions.append(func.lower(Candidate.primary_domain) == primary_domain.strip().lower())
    if skills:
        raw_skills = [s.strip() for s in skills.split(",") if s.strip()]
        norm_filter_skills = normalize_skill_list(raw_skills, alias_map)
        for idx, skill in enumerate(norm_filter_skills):
            conditions.append(_skill_filter_condition(skill, f"hsk_{idx}"))
    if min_years is not None:
        conditions.append(Candidate.years_experience >= min_years)
    if max_years is not None:
        conditions.append(Candidate.years_experience <= max_years)

    stmt = select(Candidate).options(selectinload(Candidate.resume_file))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    semantic_enabled = bool(settings.ENABLE_SEMANTIC_SEARCH)
    query_embedding: Optional[List[float]] = None
    if query_text and semantic_enabled:
        query_embedding = await generate_embedding(query_text)
    semantic_used = query_embedding is not None

    if not query_text:
        # Pure filtered listing ordered by recency
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await db.execute(count_stmt)).scalar_one())
        offset = (page - 1) * page_size
        rows = (
            await db.execute(
                stmt.order_by(Candidate.created_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()
        items = [_to_search_item(c, 0.0, 0.0, 0.0, 0.0) for c in rows]
        return CandidateSearchResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size if total else 0,
            semantic_enabled=semantic_enabled,
            semantic_used=False,
            normalized_skills_filter=norm_filter_skills,
        )

    # Compute FTS rank + pg_trgm similarity in Postgres for every filter-eligible candidate
    tsq = func.plainto_tsquery("english", query_text)
    fts_expr = func.coalesce(func.ts_rank_cd(Candidate.search_vector, tsq), 0.0).label("fts_score")
    trgm_expr = func.greatest(
        func.similarity(Candidate.full_name, query_text),
        func.similarity(Candidate.primary_domain, query_text),
        func.similarity(func.coalesce(Candidate.email, ""), query_text),
    ).label("trgm_score")

    scored_stmt = select(Candidate, fts_expr, trgm_expr).options(selectinload(Candidate.resume_file))
    if conditions:
        scored_stmt = scored_stmt.where(and_(*conditions))

    rows = (await db.execute(scored_stmt)).all()

    # Check if native pgvector distance can be queried in batch when semantic_used
    pgvec_sims: dict[UUID, float] = {}
    if (
        semantic_used
        and query_embedding
        and len(query_embedding) == settings.EMBEDDING_DIMENSIONS
        and await has_pgvector_column(db)
    ):
        vec_literal = "[" + ",".join(f"{float(v):.6f}" for v in query_embedding) + "]"
        vec_rows = (
            await db.execute(
                text(
                    "SELECT id, GREATEST(0.0, 1.0 - (embedding <=> CAST(:qvec AS vector))) AS sim "
                    "FROM candidates WHERE embedding IS NOT NULL"
                ),
                {"qvec": vec_literal},
            )
        ).all()
        for cid, sim in vec_rows:
            pgvec_sims[cid] = float(sim or 0.0)

    # Normalize query tokens for direct skill/tool boost
    q_tokens = [tok.strip() for tok in query_text.replace(",", " ").split() if tok.strip()]
    q_norm_terms = {s.lower() for s in normalize_skill_list([query_text, *q_tokens], alias_map)}
    q_lower = query_text.lower()

    ranked: List[CandidateSearchItem] = []
    for cand, fts_raw, trgm_raw in rows:
        fts_score = min(1.0, float(fts_raw or 0.0))
        trgm_score = min(1.0, float(trgm_raw or 0.0))

        # Direct skill/tool + substring match boost
        cand_skills_lower = {
            s.lower() for s in [*(cand.technical_skills or []), *(cand.tools or [])]
        }
        skill_hits = len(q_norm_terms & cand_skills_lower)
        skill_boost = min(1.0, skill_hits / max(1, len(q_tokens))) if skill_hits else 0.0
        substr_hit = (
            q_lower in (cand.full_name or "").lower()
            or q_lower in (cand.email or "").lower()
            or q_lower in (cand.primary_domain or "").lower()
            or q_lower in (cand.profile_summary or "").lower()
        )

        sem_score = 0.0
        if semantic_used and query_embedding:
            if cand.id in pgvec_sims:
                sem_score = pgvec_sims[cand.id]
            elif cand.embedding_json:
                sem_score = cosine_similarity(query_embedding, cand.embedding_json)

        if semantic_used:
            relevance = 0.35 * fts_score + 0.20 * trgm_score + 0.15 * skill_boost + 0.30 * sem_score
        else:
            relevance = 0.45 * fts_score + 0.30 * trgm_score + 0.25 * skill_boost
        if substr_hit:
            relevance = max(relevance, 0.35)

        # Keep candidates that actually matched via FTS, trgm, skill, substring, or strong semantic similarity
        if (
            fts_score > 0.0
            or trgm_score >= 0.2
            or skill_hits > 0
            or substr_hit
            or (semantic_used and sem_score >= 0.45)
        ):
            ranked.append(
                _to_search_item(
                    cand,
                    round(relevance * 100.0, 1),
                    round(fts_score, 3),
                    round(trgm_score, 3),
                    round(sem_score, 3),
                )
            )

    ranked.sort(key=lambda item: (item.relevance_score, item.created_at), reverse=True)
    total = len(ranked)
    offset = (page - 1) * page_size
    page_items = ranked[offset : offset + page_size]

    return CandidateSearchResponse(
        items=page_items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size if total else 0,
        semantic_enabled=semantic_enabled,
        semantic_used=semantic_used,
        normalized_skills_filter=norm_filter_skills,
    )


def _to_search_item(
    cand: Candidate,
    relevance: float,
    fts: float,
    trgm: float,
    semantic: float,
) -> CandidateSearchItem:
    latest = cand.work_experience[0] if cand.work_experience else None
    current_title = latest.get("job_title") if isinstance(latest, dict) else None
    current_company = latest.get("company") if isinstance(latest, dict) else None
    resume_filename = cand.resume_file.original_filename if cand.resume_file is not None else None
    return CandidateSearchItem(
        id=cand.id,
        full_name=cand.full_name,
        email=cand.email,
        phone=cand.phone,
        city=cand.city,
        primary_domain=cand.primary_domain,
        years_experience=cand.years_experience,
        technical_skills=cand.technical_skills or [],
        tools=cand.tools or [],
        is_duplicate_flagged=cand.is_duplicate_flagged,
        resume_file_id=cand.resume_file_id,
        resume_filename=resume_filename,
        created_at=cand.created_at,
        current_title=current_title,
        current_company=current_company,
        relevance_score=relevance,
        fts_score=fts,
        trgm_score=trgm,
        semantic_score=semantic,
    )


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
                "FROM candidates, "
                "jsonb_array_elements_text(COALESCE(technical_skills, '[]'::jsonb) || COALESCE(tools, '[]'::jsonb)) AS skill "
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

    # Explicitly wipe raw_parsed_data (including server-side _resume_text) before deleting row
    obj.raw_parsed_data = {}
    await db.flush()
    await db.delete(obj)
    await db.commit()

    if stored_filename:
        store = storage_backend or default_storage
        await store.delete_file(stored_filename)

    return True
