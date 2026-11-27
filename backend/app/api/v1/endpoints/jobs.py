"""
Jobs & Applications (Hiring Pipeline) endpoints.

GET    /api/v1/jobs                     - list jobs with stage counts (admin|recruiter|viewer)
POST   /api/v1/jobs                     - create job (admin|recruiter)
GET    /api/v1/jobs/{job_id}            - job detail + Kanban applications (admin|recruiter|viewer)
PUT    /api/v1/jobs/{job_id}            - update job (admin|recruiter)
DELETE /api/v1/jobs/{job_id}            - delete job (admin|recruiter)

POST   /api/v1/applications             - add candidate to job (admin|recruiter)
PATCH  /api/v1/applications/{id}/stage  - move stage + log event/audit (admin|recruiter)
DELETE /api/v1/applications/{id}        - remove application (admin|recruiter)
"""

from io import BytesIO
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.matching import list_job_matches, run_job_matching
from app.crud.pipeline import (
    create_application,
    create_job,
    delete_application,
    delete_job,
    get_job_by_id,
    get_job_detail,
    list_jobs,
    move_application_stage,
    update_job,
)
from app.crud.workflow import (
    create_interview,
    create_offer,
    list_application_interviews,
    list_application_offers,
)
from app.models.candidate import Candidate
from app.models.pipeline import JobStatus
from app.models.user import User, UserRole
from app.schemas.candidate import CandidateResponse
from app.schemas.clarity import CandidateTimelineResponse
from app.schemas.matching import JobMatchItem, JobMatchRequest
from app.schemas.pipeline import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStageUpdate,
    JobCreate,
    JobDetailResponse,
    JobResponse,
    JobUpdate,
)
from app.schemas.workflow import (
    InterviewCreate,
    InterviewResponse,
    OfferCreate,
    OfferResponse,
)
from app.services.audit import record_audit, redact_ctc_for_role, redact_for_blind_screening
from app.services.brief import get_or_generate_candidate_brief
from app.services.exports import build_shortlist_pack_pdf, build_shortlist_xlsx
from app.services.matching import compute_jd_match
from app.services.skills import load_skill_alias_map
from app.services.timeline import build_career_timeline, build_study_windows

jobs_router = APIRouter()
applications_router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


@jobs_router.get("/", response_model=List[JobResponse])
async def list_jobs_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    return await list_jobs(db, status_filter=status_filter, department=department, search=search)


@jobs_router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job_endpoint(
    job_in: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    job = await create_job(db, job_in, created_by=current_user.id)
    return JobResponse.model_validate(job)


@jobs_router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job_endpoint(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    detail = await get_job_detail(db, job_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return detail


@jobs_router.put("/{job_id}", response_model=JobResponse)
async def update_job_endpoint(
    job_id: UUID,
    job_in: JobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    job = await get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    updated = await update_job(db, job, job_in, actor_id=current_user.id)
    return JobResponse.model_validate(updated)


@jobs_router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_endpoint(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    ok = await delete_job(db, job_id, actor_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return None


@jobs_router.post("/{job_id}/match", response_model=List[JobMatchItem])
async def match_job_candidates_endpoint(
    job_id: UUID,
    payload: Optional[JobMatchRequest] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Compute deterministic 0-100 JD match scores, cache in job_matches, and return ranked results."""
    job = await get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    req = payload or JobMatchRequest()
    return await run_job_matching(
        db,
        job,
        candidate_ids=req.candidate_ids,
        include_explanations=req.include_explanations,
    )


@jobs_router.get("/{job_id}/matches", response_model=List[JobMatchItem])
async def list_job_matches_endpoint(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Return cached ranked JD match scores for a job."""
    job = await get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return await list_job_matches(db, job_id)


@jobs_router.get("/{job_id}/export/xlsx")
async def export_job_shortlist_xlsx(
    job_id: UUID,
    blind: bool = Query(False, description="Hide name, email, phone, and college/institution"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Export job pipeline & ranked match shortlist as a formatted XLSX workbook."""
    detail = await get_job_detail(db, job_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    matches = await list_job_matches(db, job_id)
    match_by_cid = {m.candidate_id: m for m in matches}
    stage_by_cid = {a.candidate_id: a.stage.value for a in detail.applications}

    # Combine pipeline candidates + matched candidates (pipeline first, then match score desc)
    ordered_ids: list[UUID] = []
    seen: set[UUID] = set()
    for a in detail.applications:
        if a.candidate_id not in seen:
            seen.add(a.candidate_id)
            ordered_ids.append(a.candidate_id)
    for m in matches:
        if m.candidate_id not in seen:
            seen.add(m.candidate_id)
            ordered_ids.append(m.candidate_id)

    cands_map: dict[UUID, Candidate] = {}
    if ordered_ids:
        cands = (
            await db.execute(select(Candidate).where(Candidate.id.in_(ordered_ids)))
        ).scalars().all()
        cands_map = {c.id: c for c in cands}

    include_ctc = current_user.role in (UserRole.admin, UserRole.recruiter)
    rows = []
    for cid in ordered_ids:
        cand = cands_map.get(cid)
        if not cand:
            continue
        resp = redact_ctc_for_role(CandidateResponse.model_validate(cand), current_user.role)
        if blind:
            resp = redact_for_blind_screening(resp)
        row_dict = resp.model_dump()
        m = match_by_cid.get(cid)
        row_dict["stage"] = stage_by_cid.get(cid, "")
        row_dict["match_score"] = m.score if m else None
        row_dict["match_explanation"] = m.explanation if m else ""
        rows.append(row_dict)

    xlsx_bytes = build_shortlist_xlsx(
        rows,
        sheet_title=detail.title[:31] or "Job Shortlist",
        include_ctc=include_ctc,
        include_job_columns=True,
        blind=blind,
    )

    await record_audit(
        db,
        user_id=current_user.id,
        action="export",
        entity="job",
        entity_id=job_id,
        metadata={
            "format": "xlsx",
            "count": len(rows),
            "blind": blind,
            "role": current_user.role.value,
        },
    )

    slug = "-".join(detail.title.lower().split())[:40] or str(job_id)[:8]
    fname = f"{slug}-blind-shortlist.xlsx" if blind else f"{slug}-shortlist.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@jobs_router.get("/{job_id}/shortlist/export/pdf")
async def export_job_shortlist_pack_pdf(
    job_id: UUID,
    candidate_ids: Optional[str] = Query(
        None, description="Optional comma-separated candidate UUIDs (defaults to pipeline + top matches)"
    ),
    blind: bool = Query(False, description="Hide name, email, phone, photo, and institution"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """
    Phase 4.5: Export a Shortlist Pack PDF (strictly one page per candidate: brief,
    timeline summary, top skills, and JD match explanation). Omits CTC for viewers; audited.
    """
    detail = await get_job_detail(db, job_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    matches = await list_job_matches(db, job_id)
    match_by_cid = {m.candidate_id: m for m in matches}
    stage_by_cid = {a.candidate_id: a.stage.value for a in detail.applications}

    ordered_ids: list[UUID] = []
    if candidate_ids:
        raw_ids = [s.strip() for s in candidate_ids.split(",") if s.strip()]
        try:
            ordered_ids = list(dict.fromkeys(UUID(i) for i in raw_ids))[:25]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid candidate UUID in `candidate_ids`",
            )
    else:
        seen: set[UUID] = set()
        for a in detail.applications:
            if a.candidate_id not in seen:
                seen.add(a.candidate_id)
                ordered_ids.append(a.candidate_id)
        for m in matches:
            if m.candidate_id not in seen:
                seen.add(m.candidate_id)
                ordered_ids.append(m.candidate_id)
        ordered_ids = ordered_ids[:25]

    cands_map: dict[UUID, Candidate] = {}
    if ordered_ids:
        cands = (
            await db.execute(select(Candidate).where(Candidate.id.in_(ordered_ids)))
        ).scalars().all()
        cands_map = {c.id: c for c in cands}

    alias_map = await load_skill_alias_map(db)
    from app.core.config import settings as app_settings

    entries = []
    for cid in ordered_ids:
        cand = cands_map.get(cid)
        if not cand:
            continue
        brief = await get_or_generate_candidate_brief(
            db, cand, force_regenerate=False, blind=blind, alias_map=alias_map
        )
        roles, gaps, overlaps, stats = build_career_timeline(
            cand.work_experience or [],
            education=cand.education or [],
        )
        study_windows, _ = build_study_windows(cand.education or [], blind=blind)
        timeline = CandidateTimelineResponse(
            candidate_id=cand.id,
            gap_threshold_months=app_settings.TIMELINE_GAP_THRESHOLD_MONTHS,
            roles=roles,
            study_windows=study_windows,
            gaps=gaps,
            overlaps=overlaps,
            tenure_stats=stats,
            consistency_checks=[],
        )

        m = match_by_cid.get(cid)
        if m is not None:
            match_dict = {
                "score": m.score,
                "breakdown": m.breakdown or {},
                "explanation": m.explanation or "",
            }
        else:
            score_val, bd_val = compute_jd_match(
                job_title=detail.title,
                job_description=detail.description,
                required_skills=detail.required_skills or [],
                nice_to_have_skills=detail.nice_to_have_skills or [],
                min_years=detail.min_years,
                max_years=detail.max_years,
                candidate_years=cand.years_experience,
                candidate_summary=cand.profile_summary,
                candidate_domain=cand.primary_domain,
                candidate_technical_skills=cand.technical_skills or [],
                candidate_tools=cand.tools or [],
                candidate_work_experience=cand.work_experience or [],
                alias_map=alias_map,
            )
            match_dict = {
                "score": score_val,
                "breakdown": bd_val,
                "explanation": bd_val.get("why") or "",
            }

        entries.append(
            {
                "candidate": CandidateResponse.model_validate(cand),
                "brief": brief,
                "timeline": timeline,
                "match": match_dict,
                "stage": stage_by_cid.get(cid),
            }
        )

    pdf_bytes = build_shortlist_pack_pdf(
        entries,
        job_title=detail.title,
        department=detail.department,
        location=detail.location,
        role=current_user.role,
        blind=blind,
    )

    await record_audit(
        db,
        user_id=current_user.id,
        action="export",
        entity="job",
        entity_id=job_id,
        metadata={
            "format": "shortlist_pack_pdf",
            "count": len(entries),
            "blind": blind,
            "role": current_user.role.value,
        },
    )

    slug = "-".join(detail.title.lower().split())[:40] or str(job_id)[:8]
    fname = f"{slug}-blind-shortlist-pack.pdf" if blind else f"{slug}-shortlist-pack.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@applications_router.post(
    "/",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_endpoint(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    app_resp, err = await create_application(
        db,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        stage=payload.stage,
        actor_id=current_user.id,
    )
    if err == "candidate_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if err == "job_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if err == "duplicate":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate is already linked to this job",
        )
    assert app_resp is not None
    return app_resp


@applications_router.patch("/{application_id}/stage", response_model=ApplicationResponse)
async def move_application_stage_endpoint(
    application_id: UUID,
    payload: ApplicationStageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    updated = await move_application_stage(
        db,
        application_id,
        to_stage=payload.stage,
        rejection_reason=payload.rejection_reason,
        reason=payload.reason,
        actor_id=current_user.id,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return updated


@applications_router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application_endpoint(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    ok = await delete_application(db, application_id, actor_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return None


@applications_router.post(
    "/{application_id}/interviews",
    response_model=InterviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_interview_endpoint(
    application_id: UUID,
    payload: InterviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    created = await create_interview(db, application_id, payload, actor_id=current_user.id)
    if not created:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return created


@applications_router.get("/{application_id}/interviews", response_model=List[InterviewResponse])
async def list_application_interviews_endpoint(
    application_id: UUID,
    blind: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    return await list_application_interviews(
        db, application_id, blind=blind, viewer_user=current_user
    )


@applications_router.post(
    "/{application_id}/offers",
    response_model=OfferResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_offer_endpoint(
    application_id: UUID,
    payload: OfferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    created = await create_offer(db, application_id, payload, actor_id=current_user.id)
    if not created:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return created


@applications_router.get("/{application_id}/offers", response_model=List[OfferResponse])
async def list_application_offers_endpoint(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Admin/recruiter only: offers contain CTC details."""
    return await list_application_offers(db, application_id)
