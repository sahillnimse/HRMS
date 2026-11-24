"""
Resume upload & parse endpoint.

POST /api/v1/resumes/upload
- Accepts PDF or DOCX via multipart/form-data
- Extracts text, parses with Gemini (structured output)
- Checks PostgreSQL for duplicates by email or phone
- Returns validated parsed JSON + duplicate flag for the Review UI
"""

import os
from uuid import UUID
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.services.file_storage import storage
from app.services.text_extraction import extract_text
from app.services.gemini_parser import GeminiParser
from app.crud.candidate import check_duplicate
from app.models.candidate import ResumeFile
from app.schemas.candidate import ResumeUploadResponse, DuplicateInfo
from app.schemas.resume import ParsedResume

router = APIRouter()

# Allowed extensions set
ALLOWED_EXTENSIONS = {ext.strip().lower() for ext in settings.ALLOWED_EXTENSIONS.split(",") if ext.strip()}
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_200_OK)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a resume (PDF or DOCX), extract text, parse with Gemini,
    check for duplicates, and return structured candidate data for review.
    """
    # --- Validate file ---
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read bytes
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max {settings.MAX_FILE_SIZE_MB} MB.",
        )

    # --- Save file to storage ---
    file_meta = await storage.save_file(
        file_bytes=file_bytes,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
    )

    # --- Persist ResumeFile metadata to DB ---
    resume_file_db = ResumeFile(
        original_filename=file_meta["original_filename"],
        stored_filename=file_meta["stored_filename"],
        file_path=file_meta["file_path"],
        file_size=file_meta["file_size"],
        content_type=file_meta["content_type"],
    )
    db.add(resume_file_db)
    await db.flush()  # get the ID without committing yet
    resume_file_id = resume_file_db.id

    # --- Extract text ---
    try:
        resume_text = await extract_text(file_bytes, file.content_type or "")
    except Exception as exc:
        # Clean up the stored file if extraction fails
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

    # --- Parse with Gemini ---
    try:
        parser = GeminiParser()
        parsed: ParsedResume = await parser.parse_resume(resume_text)
    except Exception as exc:
        await storage.delete_file(file_meta["stored_filename"])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI parsing failed: {str(exc)}",
        )

    # --- Duplicate check (by email or phone) ---
    contact = parsed.contact
    duplicate_candidate = await check_duplicate(
        db,
        email=contact.email,
        phone=contact.phone,
    )

    if duplicate_candidate:
        duplicate = DuplicateInfo(
            is_duplicate=True,
            candidate_id=duplicate_candidate.id,
            matched_field="email" if duplicate_candidate.email == contact.email else "phone",
        )
        message = "Potential duplicate candidate found. Review before saving."
    else:
        duplicate = DuplicateInfo(is_duplicate=False)
        message = "Resume parsed successfully. Review and save the candidate."

    # --- Attach raw text to raw_parsed_data for reference ---
    flat = parsed.to_flat_dict()
    flat["raw_parsed_data"] = {
        **flat,
        "_resume_text": resume_text,
        "_source_filename": filename,
        "_stored_filename": file_meta["stored_filename"],
    }

    # Commit the ResumeFile record now that parsing succeeded
    await db.commit()

    return ResumeUploadResponse(
        resume_file_id=resume_file_id,
        parsed_data=flat,
        duplicate=duplicate,
        message=message,
    )
