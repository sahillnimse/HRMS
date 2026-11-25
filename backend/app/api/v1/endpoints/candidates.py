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
from app.models.candidate import Candidate, ResumeFile
from app.models.user import User, UserRole
from app.schemas.candidate import (
    CandidateCreate,
    CandidateListItem,
    CandidateResponse,
    CandidateStats,
    CandidateUpdate,
)
from app.schemas.matching import CandidateCompareResponse, CandidateSearchResponse
from app.schemas.pipeline import (
    ActivityTimelineItem,
    ApplicationResponse,
    CandidateNoteCreate,
    CandidateNoteResponse,
)
from app.services.audit import record_audit, redact_ctc_for_role
from app.services.file_storage import storage

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


@router.get("/compare", response_model=CandidateCompareResponse)
async def compare_candidates_endpoint(
    ids: str = Query(..., description="Comma-separated list of 2 to 3 candidate UUIDs"),
    job_id: Optional[UUID] = Query(None, description="Optional job ID to include cached match scores"),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Get a single candidate's full profile, record a view audit log, and redact CTC for viewers."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    await record_audit(
        db,
        user_id=current_user.id,
        action="view",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"role": current_user.role.value},
    )
    resp = CandidateResponse.model_validate(candidate)
    return redact_ctc_for_role(resp, current_user.role)


@router.get("/{candidate_id}/export", response_model=CandidateResponse)
async def export_candidate_json(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Audited JSON export of a candidate profile (respects viewer CTC redaction)."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    await record_audit(
        db,
        user_id=current_user.id,
        action="export",
        entity="candidate",
        entity_id=candidate.id,
        metadata={"format": "json", "role": current_user.role.value},
    )
    resp = CandidateResponse.model_validate(candidate)
    return redact_ctc_for_role(resp, current_user.role)


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
        metadata={},
    )
    return None
