"""
Candidate CRUD endpoints (all authenticated with role-based access control).

GET    /api/v1/candidates            - list with search/filter/pagination (admin|recruiter|viewer)
GET    /api/v1/candidates/stats      - aggregate metrics (admin|recruiter|viewer)
GET    /api/v1/candidates/{id}       - get single candidate (admin|recruiter|viewer)
GET    /api/v1/candidates/{id}/resume - stream candidate's resume file (admin|recruiter|viewer)
POST   /api/v1/candidates            - create from Review UI (admin|recruiter)
PUT    /api/v1/candidates/{id}       - update (admin|recruiter)
DELETE /api/v1/candidates/{id}       - delete (admin|recruiter)
"""

from io import BytesIO
from pathlib import Path
from typing import Optional
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
    update_candidate,
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
from app.services.file_storage import storage

router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


def _to_list_item(candidate: Candidate) -> CandidateListItem:
    """Build a dashboard row, surfacing the most recent role for display."""
    item = CandidateListItem.model_validate(candidate)
    latest = candidate.work_experience[0] if candidate.work_experience else None
    if isinstance(latest, dict):
        item.current_title = latest.get("job_title") or None
        item.current_company = latest.get("company") or None
    return item


@router.post("/", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate_endpoint(
    candidate_in: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Save a reviewed candidate to PostgreSQL."""
    matches = await find_duplicates(
        db,
        email=str(candidate_in.email) if candidate_in.email else None,
        phone=candidate_in.phone,
        full_name=candidate_in.full_name,
    )
    exact_matches = [m for m in matches if "email" in m.matched_fields or "phone" in m.matched_fields]

    if exact_matches and not candidate_in.allow_duplicate:
        top = exact_matches[0]
        fields = ", ".join(top.matched_fields)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Candidate already exists (matched {top.full_name} by {fields})",
        )

    flagged = bool(candidate_in.is_duplicate_flagged or matches)
    return await create_candidate(db, candidate_in, is_duplicate_flagged=flagged)


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


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Get a single candidate's full profile."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


@router.get("/{candidate_id}/resume")
async def stream_candidate_resume(
    candidate_id: UUID,
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Authenticated streaming download/preview of a candidate's attached resume file."""
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

    safe_name = Path(rf.original_filename).name.replace('"', "")
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type=rf.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'{disposition}; filename="{safe_name}"'},
    )


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate_endpoint(
    candidate_id: UUID,
    candidate_in: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Update an existing candidate (HR edits after save or duplicate update)."""
    candidate = await get_candidate_by_id(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await update_candidate(db, candidate, candidate_in)


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Delete a candidate."""
    success = await delete_candidate(db, candidate_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return None
