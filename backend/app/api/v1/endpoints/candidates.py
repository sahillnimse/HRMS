"""
Candidate CRUD, audited export, notes, applications, and activity endpoints.

GET    /api/v1/candidates                     - list with search/filter/pagination (admin|recruiter|viewer)
GET    /api/v1/candidates/stats               - aggregate metrics (admin|recruiter|viewer)
GET    /api/v1/candidates/{id}                - get profile + audit view + redact CTC for viewer
GET    /api/v1/candidates/{id}/export         - export JSON + audit export + redact CTC for viewer
GET    /api/v1/candidates/{id}/resume         - stream resume + audit view/export
GET    /api/v1/candidates/{id}/applications   - list jobs/stages for candidate
GET    /api/v1/candidates/{id}/notes          - list candidate notes
POST   /api/v1/candidates/{id}/notes          - add candidate note (admin|recruiter)
DELETE /api/v1/candidates/{id}/notes/{noteId} - delete candidate note (admin or author)
GET    /api/v1/candidates/{id}/activity       - unified activity timeline
POST   /api/v1/candidates                     - create from Review UI (admin|recruiter)
PUT    /api/v1/candidates/{id}                - update + audit edit (admin|recruiter)
DELETE /api/v1/candidates/{id}                - delete + file cleanup + audit delete (admin|recruiter)
"""

from io import BytesIO
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.candidate import (
    create_candidate,
    delete_candidate,
    find_duplicates,
    get_candidate_by_id,
    get_candidate_stats,
    get_candidates,
    search_candidates_hybrid,
    update_candidate,
)
from app.crud.matching import list_job_matches
from app.crud.pipeline import (
    create_candidate_note,
    delete_candidate_note,
    get_candidate_activity,
    list_candidate_applications,
    list_candidate_notes,
)
from app.crud.backlog import list_candidate_pools
from app.crud.workflow import get_candidate_scorecard_summary, list_candidate_emails
from app.models.pipeline import Job
from app.schemas.backlog import (
    InterviewQuestionsRequest,
    InterviewQuestionsResponse,
    NLSearchRequest,
    NLSearchResponse,
    TalentPoolResponse,
)
from app.schemas.workflow import EmailLogResponse, ScorecardAggregate
from app.models.candidate import Candidate, ResumeFile
from app.models.user import User, UserRole
from app.schemas.candidate import (
    CandidateCreate,
    CandidateListItem,
    CandidateResponse,
    CandidateStats,
    CandidateUpdate,
    SectionRemapResponse,
    _strip_internal_resume_text,
)
from app.services.bulk_parse import parse_resume_pipeline
from app.services.remap import remap_candidate_sections
from app.schemas.clarity import CandidateBriefResponse, CandidateTimelineResponse
from app.schemas.matching import CandidateCompareResponse, CandidateSearchResponse
from app.schemas.pipeline import (
    ActivityTimelineItem,
    ApplicationResponse,
    CandidateNoteCreate,
    CandidateNoteResponse,
)
from app.services.audit import (
    blind_candidate_label,
    record_audit,
    redact_ctc_for_role,
    redact_for_blind_screening,
)
from app.services.brief import get_or_generate_candidate_brief
from app.services.consistency import compute_skill_evidence, run_consistency_checks
from app.services.exports import build_candidate_pdf, build_shortlist_xlsx
from app.services.file_storage import storage
from app.services.interview_questions import generate_interview_questions
from app.services.nl_search import parse_nl_search_query
from app.services.skills import load_skill_alias_map
from app.services.timeline import build_career_timeline, build_study_windows

router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


def _to_list_item(candidate: Candidate) -> CandidateListItem:
    """Build a dashboard row, surfacing the most recent role and attached CV metadata."""
    item = CandidateListItem.model_validate(candidate)
    latest = candidate.work_experience[0] if candidate.work_experience else None
    if isinstance(latest, dict):
        item.current_title = latest.get("job_title") or None
        item.current_company = latest.get("company") or None
    if candidate.resume_file is not None:
        item.resume_filename = candidate.resume_file.original_filename
    return item


@router.post("/nl-search", response_model=NLSearchResponse)
async def nl_search_candidates_endpoint(
    payload: NLSearchRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """
    Natural-language candidate search (e.g. "Python, 3+ yrs, Pune, notice < 30 days"):
    parses structured filters via Gemini (with deterministic regex fallback) and runs hybrid search.
    """
    alias_map = await load_skill_alias_map(db)
    parsed, parser_mode = await parse_nl_search_query(payload.query, alias_map=alias_map)

    skills_csv = ",".join(parsed.skills) if parsed.skills else None
    search_res = await search_candidates_hybrid(
        db,
        q=parsed.semantic_query or None,
        page=payload.page,
        page_size=payload.page_size,
        primary_domain=parsed.primary_domain,
        skills=skills_csv,
        min_years=parsed.min_years,
        max_years=parsed.max_years,
        city=parsed.city,
        max_notice_days=parsed.max_notice_days,
    )

    items = search_res.items
    if payload.blind:
        items = [
            it.model_copy(
                update={
                    "full_name": blind_candidate_label(it.id),
                    "email": None,
                    "phone": None,
                }
            )
            for it in items
        ]

    return NLSearchResponse(
        original_query=payload.query,
        parser_mode=parser_mode,
        parsed_filters=parsed,
        items=items,
        total=search_res.total,
        page=search_res.page,
        page_size=search_res.page_size,
        pages=search_res.pages,
        semantic_used=search_res.semantic_used,
    )


@router.post("/admin/remap-sections", response_model=SectionRemapResponse)
async def admin_remap_sections_endpoint(
    dry_run: bool = Query(True, description="Preview changes without modifying the database (default true)"),
    candidate_id: Optional[UUID] = Query(None, description="Optional single candidate UUID"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    Admin-only re-mapping of existing candidates' education dates, work employment_type,
    and projects from stored resume text/files. Dry-run by default; skips hand-edited sections.
    """
    return await remap_candidate_sections(
        db,
        dry_run=dry_run,
        candidate_id=candidate_id,
        limit=limit,
        actor_id=current_user.id,
    )


@router.post("/", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate_endpoint(
    candidate_in: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Save a reviewed candidate to PostgreSQL."""
    matches = await find_duplicates(
        db,
        email=str(candidate_in.email) if candidate_in.email else None,
        phone=candidate_in.phone,
        full_name=candidate_in.full_name,
    )
    exact_matches = [
        m for m in matches if "email" in m.matched_fields or "phone" in m.matched_fields
    ]

    if exact_matches and not candidate_in.allow_duplicate:
        top = exact_matches[0]
        fields = ", ".join(top.matched_fields)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Candidate already exists (matched {top.full_name} by {fields})",
        )

    flagged = bool(candidate_in.is_duplicate_flagged or matches)
    created = await create_candidate(db, candidate_in, is_duplicate_flagged=flagged)
    await record_audit(
        db,
        user_id=current_user.id,
        action="create",
        entity="candidate",
        entity_id=created.id,
        metadata={"full_name": created.full_name, "is_duplicate_flagged": flagged},
    )
    return created


@router.get("/", response_model=dict)
async def list_candidates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search name, email, or domain"),
    primary_domain: Optional[str] = Query(None, description="Filter by primary domain"),
    skills: Optional[str] = Query(None, description="Comma-separated skills to match"),
    min_years: Optional[float] = Query(None, ge=0, description="Min years experience"),
    max_years: Optional[float] = Query(None, ge=0, description="Max years experience"),
):
    """Searchable, filterable, paginated candidate list for the dashboard."""
    items, total = await get_candidates(
        db,
        page=page,
        page_size=page_size,
        search=search,
        primary_domain=primary_domain,
        skills=skills,
        min_years=min_years,
        max_years=max_years,
    )
    return {
        "items": [_to_list_item(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/stats", response_model=CandidateStats)
async def candidate_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Aggregate talent-pool metrics for the dashboard."""
    return await get_candidate_stats(db)


@router.get("/search", response_model=CandidateSearchResponse)
async def search_candidates_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
    q: Optional[str] = Query(None, description="Hybrid full-text, trigram & semantic search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    primary_domain: Optional[str] = Query(None),
    skills: Optional[str] = Query(None, description="Comma-separated skills (case-insensitive, covers tech & tools)"),
    min_years: Optional[float] = Query(None, ge=0),
    max_years: Optional[float] = Query(None, ge=0),
):
    """Hybrid candidate search (FTS + pg_trgm + normalized skills + optional pgvector semantic)."""
    return await search_candidates_hybrid(
        db,
        q=q,
        page=page,
        page_size=page_size,
        primary_domain=primary_domain,
        skills=skills,
        min_years=min_years,
        max_years=max_years,
    )


@router.get("/export/xlsx")
async def export_candidates_xlsx(
    ids: Optional[str] = Query(None, description="Optional comma-separated candidate UUIDs"),
    blind: bool = Query(False, description="Hide name, email, phone, and college/institution"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Export candidates shortlist as a formatted XLSX workbook (respects viewer & blind mode)."""
    stmt = select(Candidate).order_by(Candidate.created_at.desc())
    if ids:
        raw_ids = [s.strip() for s in ids.split(",") if s.strip()]
        try:
            parsed_ids = [UUID(i) for i in raw_ids]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid candidate UUID in `ids`",
            )
        stmt = stmt.where(Candidate.id.in_(parsed_ids))
    else:
        stmt = stmt.limit(500)

    cands = list((await db.execute(stmt)).scalars().all())
    include_ctc = current_user.role in (UserRole.admin, UserRole.recruiter)

    rows = []
    for c in cands:
        resp = redact_ctc_for_role(CandidateResponse.model_validate(c), current_user.role)
        if blind:
            resp = redact_for_blind_screening(resp)
        rows.append(resp.model_dump())

    xlsx_bytes = build_shortlist_xlsx(
        rows,
        sheet_title="Candidates Shortlist",
        include_ctc=include_ctc,
        include_job_columns=False,
        blind=blind,
    )

    await record_audit(
        db,
        user_id=current_user.id,
        action="export",
        entity="candidate",
        entity_id="shortlist",
        metadata={
            "format": "xlsx",
            "count": len(rows),
            "blind": blind,
            "role": current_user.role.value,
        },
    )

    fname = "candidates-blind-shortlist.xlsx" if blind else "candidates-shortlist.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/compare", response_model=CandidateCompareResponse)
async def compare_candidates_endpoint(
    ids: str = Query(..., description="Comma-separated list of 2 to 3 candidate UUIDs"),
    job_id: Optional[UUID] = Query(None, description="Optional job ID to include cached match scores"),
    blind: bool = Query(False, description="Anonymize candidate identities for blind screening"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Compare 2 to 3 candidates side-by-side (audits views and redacts CTC for viewers)."""
    raw_ids = [s.strip() for s in ids.split(",") if s.strip()]
    try:
        parsed_ids = list(dict.fromkeys(UUID(i) for i in raw_ids))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate UUID in `ids`",
        )
    if len(parsed_ids) < 2 or len(parsed_ids) > 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select between 2 and 3 candidates to compare",
        )

    candidates_out: List[CandidateResponse] = []
    skill_sets: List[set[str]] = []
    canonical_display: dict[str, str] = {}

    for cid in parsed_ids:
        cand = await get_candidate_by_id(db, cid)
        if not cand:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate {cid} not found",
            )
        await record_audit(
            db,
            user_id=current_user.id,
            action="view",
            entity="candidate",
            entity_id=cand.id,
            metadata={"role": current_user.role.value, "context": "compare"},
            commit=False,
        )
        resp = redact_ctc_for_role(CandidateResponse.model_validate(cand), current_user.role)
        if blind:
            resp = redact_for_blind_screening(resp)
        candidates_out.append(resp)

        c_skills = [*(resp.technical_skills or []), *(resp.tools or [])]
        low_set: set[str] = set()
        for sk in c_skills:
            low = sk.lower()
            low_set.add(low)
            canonical_display.setdefault(low, sk)
        skill_sets.append(low_set)

    await db.commit()

    shared_keys = set.intersection(*skill_sets) if skill_sets else set()
    shared_skills = sorted(canonical_display[k] for k in shared_keys)

    job_match_map = {}
    if job_id is not None:
        cached = await list_job_matches(db, job_id, candidate_ids=parsed_ids)
        job_match_map = {str(m.candidate_id): m for m in cached}

    return CandidateCompareResponse(
        candidates=candidates_out,
        shared_skills=shared_skills,
        job_matches=job_match_map,
    )


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    blind: bool = Query(False, description="Anonymize identity fields for blind screening"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Get a single candidate's full profile, record a view audit log, and redact CTC/blind fields."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    await record_audit(
        db,
        user_id=current_user.id,
        action="view",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"role": current_user.role.value, "blind": blind},
    )
    resp = redact_ctc_for_role(CandidateResponse.model_validate(candidate), current_user.role)
    if blind:
        resp = redact_for_blind_screening(resp)
    return resp


@router.get("/{candidate_id}/export", response_model=CandidateResponse)
async def export_candidate_json(
    candidate_id: UUID,
    blind: bool = Query(False, description="Anonymize identity fields for blind screening"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Audited JSON export of a candidate profile (respects viewer CTC & blind redaction)."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    await record_audit(
        db,
        user_id=current_user.id,
        action="export",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"format": "json", "blind": blind, "role": current_user.role.value},
    )
    resp = redact_ctc_for_role(CandidateResponse.model_validate(candidate), current_user.role)
    if blind:
        resp = redact_for_blind_screening(resp)
    return resp


@router.get("/{candidate_id}/export/pdf")
async def export_candidate_pdf(
    candidate_id: UUID,
    blind: bool = Query(False, description="Hide name, email, phone, and college/institution"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Audited one-page executive PDF dossier export (respects viewer CTC & blind redaction)."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    pdf_bytes = build_candidate_pdf(
        CandidateResponse.model_validate(candidate),
        role=current_user.role,
        blind=blind,
    )

    await record_audit(
        db,
        user_id=current_user.id,
        action="export",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"format": "pdf", "blind": blind, "role": current_user.role.value},
    )

    slug = (
        f"candidate-{str(candidate.id)[:6]}-blind"
        if blind
        else "-".join(candidate.full_name.lower().split())[:48] or str(candidate.id)[:8]
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'},
    )


@router.get("/{candidate_id}/resume")
async def stream_candidate_resume(
    candidate_id: UUID,
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Authenticated streaming download/preview of a candidate's attached resume file (audited)."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if not candidate.resume_file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate has no attached resume file",
        )

    res = await db.execute(select(ResumeFile).where(ResumeFile.id == candidate.resume_file_id))
    rf = res.scalar_one_or_none()
    if not rf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume file record not found")

    try:
        file_bytes = await storage.read_file(rf.stored_filename)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored resume file is missing")

    await record_audit(
        db,
        user_id=current_user.id,
        action="export" if download else "view",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"resume_file_id": str(rf.id), "download": download},
    )

    safe_name = Path(rf.original_filename).name.replace('"', "")
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type=rf.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'{disposition}; filename="{safe_name}"'},
    )


@router.get("/{candidate_id}/brief", response_model=CandidateBriefResponse)
async def get_candidate_brief_endpoint(
    candidate_id: UUID,
    blind: bool = Query(False, description="Mask identifying tokens for blind screening"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Return cached Candidate Brief, generating lazily if missing or source data changed."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await get_or_generate_candidate_brief(db, candidate, force_regenerate=False, blind=blind)


@router.post("/{candidate_id}/brief/regenerate", response_model=CandidateBriefResponse)
async def regenerate_candidate_brief_endpoint(
    candidate_id: UUID,
    blind: bool = Query(False, description="Mask identifying tokens for blind screening"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Force-regenerate a candidate's brief (admin/recruiter only)."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    brief = await get_or_generate_candidate_brief(db, candidate, force_regenerate=True, blind=blind)
    await record_audit(
        db,
        user_id=current_user.id,
        action="brief_regenerate",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"model": brief.model},
    )
    return brief


@router.get("/{candidate_id}/timeline", response_model=CandidateTimelineResponse)
async def get_candidate_timeline_endpoint(
    candidate_id: UUID,
    gap_months: Optional[int] = Query(
        None, ge=1, le=36, description="Gap threshold in months (defaults to TIMELINE_GAP_THRESHOLD_MONTHS)"
    ),
    blind: bool = Query(False, description="Mask institution names in study windows for blind screening"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Return normalized career timeline, study windows, gaps, overlaps, tenure stats, skill evidence, and neutral consistency checks."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    from app.core.config import settings as app_settings

    effective_gap = gap_months if gap_months is not None else app_settings.TIMELINE_GAP_THRESHOLD_MONTHS
    roles, gaps, overlaps, stats = build_career_timeline(
        candidate.work_experience or [],
        education=candidate.education or [],
        gap_threshold_months=effective_gap,
    )
    study_windows, _ = build_study_windows(candidate.education or [], blind=blind)
    llm_years = None
    if isinstance(candidate.raw_parsed_data, dict):
        raw_llm = candidate.raw_parsed_data.get("_llm_years_experience")
        if isinstance(raw_llm, (int, float)):
            llm_years = float(raw_llm)

    alias_map = await load_skill_alias_map(db)
    projects = getattr(candidate, "projects", None) or []
    skill_evidence = compute_skill_evidence(
        technical_skills=candidate.technical_skills or [],
        tools=candidate.tools or [],
        profile_summary=candidate.profile_summary or "",
        work_experience=candidate.work_experience or [],
        projects=projects,
        certifications=candidate.certifications or [],
        education=candidate.education or [],
        alias_map=alias_map,
    )
    checks = run_consistency_checks(
        roles=roles,
        gaps=gaps,
        overlaps=overlaps,
        tenure_stats=stats,
        stated_years=float(candidate.years_experience or 0.0),
        llm_stated_years=llm_years,
        work_experience=candidate.work_experience or [],
        profile_summary=candidate.profile_summary or "",
        technical_skills=candidate.technical_skills or [],
        tools=candidate.tools or [],
        projects=projects,
        certifications=candidate.certifications or [],
        education=candidate.education or [],
        alias_map=alias_map,
        skill_evidence=skill_evidence,
    )
    return CandidateTimelineResponse(
        candidate_id=candidate.id,
        gap_threshold_months=effective_gap,
        roles=roles,
        study_windows=study_windows,
        gaps=gaps,
        overlaps=overlaps,
        tenure_stats=stats,
        consistency_checks=checks,
        skill_evidence=skill_evidence,
    )


@router.post("/{candidate_id}/interview-questions", response_model=InterviewQuestionsResponse)
async def generate_interview_questions_endpoint(
    candidate_id: UUID,
    payload: InterviewQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """
    Generate tailored, fair interview questions grounded in the candidate's projects,
    skills, optional target JD skill-gaps, and neutral 'worth verifying' items.
    """
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    job_obj: Optional[Job] = None
    if payload.job_id is not None:
        job_obj = (
            await db.execute(select(Job).where(Job.id == payload.job_id))
        ).scalar_one_or_none()
        if not job_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    alias_map = await load_skill_alias_map(db)
    return await generate_interview_questions(
        candidate,
        job=job_obj,
        alias_map=alias_map,
        count=payload.count,
        blind=payload.blind,
    )


@router.get("/{candidate_id}/talent-pools", response_model=List[TalentPoolResponse])
async def get_candidate_talent_pools_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await list_candidate_pools(db, candidate_id)


@router.get("/{candidate_id}/applications", response_model=List[ApplicationResponse])
async def get_candidate_applications(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await list_candidate_applications(db, candidate_id)


@router.get("/{candidate_id}/scorecard-summary", response_model=ScorecardAggregate)
async def get_candidate_scorecard_summary_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await get_candidate_scorecard_summary(db, candidate_id)


@router.get("/{candidate_id}/emails", response_model=List[EmailLogResponse])
async def get_candidate_emails_endpoint(
    candidate_id: UUID,
    blind: bool = Query(False, description="Mask recipient email and identifying subject tokens"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await list_candidate_emails(db, candidate_id, blind=blind)


@router.get("/{candidate_id}/notes", response_model=List[CandidateNoteResponse])
async def get_candidate_notes_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await list_candidate_notes(db, candidate_id)


@router.post(
    "/{candidate_id}/notes",
    response_model=CandidateNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate_note_endpoint(
    candidate_id: UUID,
    note_in: CandidateNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await create_candidate_note(
        db, candidate_id=candidate_id, author_id=current_user.id, note_in=note_in
    )


@router.delete("/{candidate_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate_note_endpoint(
    candidate_id: UUID,
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    ok, err = await delete_candidate_note(
        db,
        candidate_id=candidate_id,
        note_id=note_id,
        actor_id=current_user.id,
        is_admin=current_user.role == UserRole.admin,
    )
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if err == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete another user's note")
    return None


@router.get("/{candidate_id}/activity", response_model=List[ActivityTimelineItem])
async def get_candidate_activity_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await get_candidate_activity(db, candidate_id)


@router.post("/{candidate_id}/reparse")
async def reparse_candidate_resume_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """
    Re-parse a candidate's attached saved resume file (with OCR fallback + structured AI parser)
    and return a preview payload WITHOUT mutating the database, so the recruiter can review
    and save in Edit Details.
    """
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if not candidate.resume_file_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate does not have a saved resume file attached.",
        )

    rf = (
        await db.execute(select(ResumeFile).where(ResumeFile.id == candidate.resume_file_id))
    ).scalar_one_or_none()
    if not rf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved resume file not found")

    try:
        file_bytes = await storage.read_file(rf.stored_filename)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved resume file is missing from storage.",
        )

    try:
        flat, _dup, ocr_used = await parse_resume_pipeline(
            db,
            file_bytes=file_bytes,
            filename=rf.original_filename,
            content_type=rf.content_type or "",
            stored_filename=rf.stored_filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI re-parsing failed: {str(exc)}",
        )

    await record_audit(
        db,
        user_id=current_user.id,
        action="reparse_preview",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"ocr_used": ocr_used},
    )
    return {
        "candidate_id": str(candidate.id),
        "ocr_used": ocr_used,
        "parsed_data": _strip_internal_resume_text(flat),
    }


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate_endpoint(
    candidate_id: UUID,
    candidate_in: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Update an existing candidate and write an edit audit log."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    updated_fields = sorted(candidate_in.model_dump(exclude_unset=True).keys())
    updated = await update_candidate(db, candidate, candidate_in)
    await record_audit(
        db,
        user_id=current_user.id,
        action="edit",
        entity="candidate",
        entity_id=updated.id,
        metadata={"updated_fields": updated_fields},
    )
    return updated


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Delete a candidate, its resume file, and write a delete audit log."""
    success = await delete_candidate(db, candidate_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    await record_audit(
        db,
        user_id=current_user.id,
        action="delete",
        entity="candidate",
        entity_id=candidate_id,
        metadata={"reason": "manual_delete", "pii_wiped": True},
    )
    return None
