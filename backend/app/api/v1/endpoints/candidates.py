"""
Candidate CRUD endpoints.

GET    /api/v1/candidates            - list with search/filter/pagination
GET    /api/v1/candidates/{id}       - get single candidate
POST   /api/v1/candidates            - create (from Review UI)
PUT    /api/v1/candidates/{id}       - update
DELETE /api/v1/candidates/{id}       - delete
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.crud.candidate import (
    create_candidate,
    get_candidate_by_id,
    update_candidate,
    get_candidates,
    get_candidate_stats,
    delete_candidate,
    check_duplicate,
)
from app.models.candidate import Candidate
from app.schemas.candidate import (
    CandidateCreate,
    CandidateUpdate,
    CandidateResponse,
    CandidateListItem,
    CandidateStats,
)

router = APIRouter()


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
):
    """Save a reviewed candidate to PostgreSQL."""
    # Re-check duplicate on save to avoid race conditions
    existing = await check_duplicate(db, email=candidate_in.email, phone=candidate_in.phone)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Candidate already exists (matched by {'email' if existing.email == candidate_in.email else 'phone'})",
        )

    return await create_candidate(db, candidate_in)


@router.get("/", response_model=dict)
async def list_candidates(
    db: AsyncSession = Depends(get_db),
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
async def candidate_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate talent-pool metrics for the dashboard."""
    return await get_candidate_stats(db)


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single candidate's full profile."""
    candidate = await get_candidate_by_id(db, str(candidate_id))
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate_endpoint(
    candidate_id: UUID,
    candidate_in: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing candidate (HR edits after save)."""
    candidate = await get_candidate_by_id(db, str(candidate_id))
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return await update_candidate(db, candidate, candidate_in)


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate_endpoint(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a candidate."""
    success = await delete_candidate(db, str(candidate_id))
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return None
