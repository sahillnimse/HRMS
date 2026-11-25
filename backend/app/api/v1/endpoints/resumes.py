"""
Resume upload, authenticated file streaming, and admin orphan cleanup endpoints.

POST /api/v1/resumes/upload                - Upload PDF/DOCX, parse, check duplicates (admin|recruiter)
GET  /api/v1/resumes/{resume_file_id}/file - Authenticated resume stream (admin|recruiter|viewer)
POST /api/v1/resumes/cleanup               - Trigger orphan pending file cleanup (admin)
"""

from io import BytesIO
import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.config import settings
from app.crud.candidate import find_duplicates
from app.models.candidate import ResumeFile, ResumeFileStatus
from app.models.user import User, UserRole
from app.schemas.candidate import DuplicateInfo, ResumeUploadResponse
from app.schemas.resume import ParsedResume
from app.services.cleanup import cleanup_orphan_resumes
from app.services.experience import compute_years_experience
from app.services.file_storage import storage
from app.services.gemini_parser import GeminiParser
from app.services.text_extraction import extract_text

router = APIRouter()

ALLOWED_EXTENSIONS = {
    ext.strip().lower() for ext in settings.ALLOWED_EXTENSIONS.split(",") if ext.strip()
}
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_200_OK)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """
    Upload a resume (PDF or DOCX), extract text, parse with AI, deterministically
    calculate years_experience, find ALL potential duplicates (email, phone, fuzzy name),
    and return structured candidate data for human review.
    """
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max {settings.MAX_FILE_SIZE_MB} MB.",
        )

    # Save file via storage abstraction
    file_meta = await storage.save_file(
        file_bytes=file_bytes,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
    )

    # Persist ResumeFile metadata with status='pending' until attached on save
    resume_file_db = ResumeFile(
        original_filename=file_meta["original_filename"],
        stored_filename=file_meta["stored_filename"],
        file_path=file_meta["file_path"],
        file_size=file_meta["file_size"],
        content_type=file_meta["content_type"],
        status=ResumeFileStatus.pending.value,
    )
    db.add(resume_file_db)
    await db.flush()
    resume_file_id = resume_file_db.id

    # Extract text
    try:
        resume_text = await extract_text(file_bytes, file.content_type or "")
    except Exception as exc:
        await storage.delete_file(file_meta["stored_filename"])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract text from resume: {str(exc)}",
        )

    if not resume_text or len(resume_text.strip()) < 10:
        await storage.delete_file(file_meta["stored_filename"])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract readable text from the resume.",
        )

    # Parse with AI
    try:
        parser = GeminiParser()
        parsed: ParsedResume = await parser.parse_resume(resume_text)
    except Exception as exc:
        await storage.delete_file(file_meta["stored_filename"])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI parsing failed: {str(exc)}",
        )

    flat = parsed.to_flat_dict()

    # Deterministic years_experience computation (keep LLM estimate in raw_parsed_data)
    llm_years = flat["years_experience"]
    computed_years = compute_years_experience(flat["work_experience"])
    flat["years_experience"] = computed_years

    # Duplicate detection across normalized email, normalized phone, and fuzzy name (pg_trgm)
    matches = await find_duplicates(
        db,
        email=flat.get("email"),
        phone=flat.get("phone"),
        full_name=flat.get("full_name"),
    )

    if matches:
        top = matches[0]
        duplicate = DuplicateInfo(
            is_duplicate=True,
            candidate_id=top.candidate_id,
            matched_field=top.matched_fields[0] if top.matched_fields else None,
            matches=matches,
        )
        message = (
            f"Found {len(matches)} potential duplicate candidate"
            f"{'s' if len(matches) != 1 else ''}. Review and choose to update existing or save as new."
        )
    else:
        duplicate = DuplicateInfo(is_duplicate=False, matches=[])
        message = "Resume parsed successfully. Review and save the candidate."

    flat["raw_parsed_data"] = {
        **flat,
        "_llm_years_experience": llm_years,
        "_computed_years_experience": computed_years,
        "_resume_text": resume_text,
        "_source_filename": filename,
        "_stored_filename": file_meta["stored_filename"],
    }

    await db.commit()

    return ResumeUploadResponse(
        resume_file_id=resume_file_id,
        parsed_data=flat,
        duplicate=duplicate,
        message=message,
    )


@router.get("/{resume_file_id}/file")
async def stream_resume_file(
    resume_file_id: UUID,
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """Stream an uploaded resume file through the configured storage layer (authenticated)."""
    res = await db.execute(select(ResumeFile).where(ResumeFile.id == resume_file_id))
    rf = res.scalar_one_or_none()
    if not rf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume file not found")

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


@router.post("/cleanup", response_model=dict)
async def trigger_orphan_cleanup(
    max_age_hours: int = Query(default=24, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    """Admin-only: immediately purge pending resume files older than `max_age_hours`."""
    deleted = await cleanup_orphan_resumes(db, max_age_hours=max_age_hours)
    return {"deleted": deleted, "max_age_hours": max_age_hours}
