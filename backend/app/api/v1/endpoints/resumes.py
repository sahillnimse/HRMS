"""
Resume upload (single + Phase 3 bulk queue), authenticated file streaming,
pending resume deletion, and admin orphan cleanup endpoints.

POST   /api/v1/resumes/upload                - Upload PDF/DOCX, extract (+OCR), parse, check duplicates
POST   /api/v1/resumes/bulk-upload           - Upload multiple resumes into parse_jobs queue
GET    /api/v1/resumes/parse-jobs            - Poll bulk parse jobs (filterable by batch_id)
GET    /api/v1/resumes/parse-jobs/{job_id}   - Poll a single parse job
GET    /api/v1/resumes/pending               - List unsaved pending resumes
GET    /api/v1/resumes/{resume_file_id}/file - Authenticated resume stream
DELETE /api/v1/resumes/{resume_file_id}      - Delete an unattached pending resume file
POST   /api/v1/resumes/cleanup               - Trigger orphan pending file cleanup (admin)
"""

import base64
import hmac
from io import BytesIO
import os
from pathlib import Path
from typing import List, Optional
import uuid
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.config import settings
from app.core.security import decode_access_token
from app.crud.backlog import list_inbound_email_logs
from app.crud.user import get_user_by_id
from app.models.backlog import InboundEmailLog
from app.models.candidate import Candidate, ParseJob, ParseJobStatus, ResumeFile, ResumeFileStatus
from app.models.user import User, UserRole
from app.schemas.backlog import InboundEmailLogResponse, InboundEmailWebhookPayload
from app.schemas.candidate import (
    BulkUploadResponse,
    ParseJobItem,
    PendingResumeItem,
    ResumeUploadResponse,
)
from app.services.audit import record_audit
from app.services.bulk_parse import enqueue_parse_jobs, parse_resume_pipeline
from app.services.cleanup import cleanup_orphan_resumes
from app.services.file_storage import storage
from app.services.gemini_parser import GeminiParser
from app.services.text_extraction import extract_text as _default_extract_text
from app.services.text_extraction import extract_text_with_meta

extract_text = _default_extract_text

router = APIRouter()

ALLOWED_EXTENSIONS = {
    ext.strip().lower() for ext in settings.ALLOWED_EXTENSIONS.split(",") if ext.strip()
}
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


def _validate_upload(filename: str, size: int) -> None:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' too large. Max {settings.MAX_FILE_SIZE_MB} MB.",
        )


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_200_OK)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """
    Upload a resume (PDF or DOCX), extract text (with OCR fallback for scanned PDFs),
    parse with AI, deterministically calculate years_experience, find ALL potential
    duplicates, and return structured candidate data for human review.
    """
    filename = file.filename or ""
    file_bytes = await file.read()
    _validate_upload(filename, len(file_bytes))

    file_meta = await storage.save_file(
        file_bytes=file_bytes,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
    )

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

    try:
        extractor = extract_text if extract_text is not _default_extract_text else extract_text_with_meta
        flat, duplicate, ocr_used = await parse_resume_pipeline(
            db,
            file_bytes=file_bytes,
            filename=filename,
            content_type=file.content_type or "",
            stored_filename=file_meta["stored_filename"],
            extract_fn=extractor,
            parser_cls=GeminiParser,
        )
    except ValueError as exc:
        await storage.delete_file(file_meta["stored_filename"])
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        await storage.delete_file(file_meta["stored_filename"])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI parsing failed: {str(exc)}",
        )

    if duplicate.is_duplicate:
        n = len(duplicate.matches)
        message = (
            f"Found {n} potential duplicate candidate{'s' if n != 1 else ''}. "
            "Review and choose to update existing or save as new."
        )
    else:
        message = "Resume parsed successfully. Review and save the candidate."

    await db.commit()

    return ResumeUploadResponse(
        resume_file_id=resume_file_id,
        parsed_data=flat,
        duplicate=duplicate,
        ocr_used=ocr_used,
        message=message,
    )


@router.post("/bulk-upload", response_model=BulkUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def bulk_upload_resumes(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Upload multiple PDF/DOCX resumes and enqueue background parsing jobs."""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
    if len(files) > settings.BULK_UPLOAD_MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.BULK_UPLOAD_MAX_FILES} files per batch.",
        )

    batch_id = uuid.uuid4()
    created_jobs: List[ParseJob] = []

    for f in files:
        filename = f.filename or "resume.pdf"
        file_bytes = await f.read()
        _validate_upload(filename, len(file_bytes))

        file_meta = await storage.save_file(
            file_bytes=file_bytes,
            original_filename=filename,
            content_type=f.content_type or "application/octet-stream",
        )
        rf = ResumeFile(
            original_filename=file_meta["original_filename"],
            stored_filename=file_meta["stored_filename"],
            file_path=file_meta["file_path"],
            file_size=file_meta["file_size"],
            content_type=file_meta["content_type"],
            status=ResumeFileStatus.pending.value,
        )
        db.add(rf)
        await db.flush()

        job = ParseJob(
            batch_id=batch_id,
            resume_file_id=rf.id,
            original_filename=rf.original_filename,
            status=ParseJobStatus.queued.value,
            created_by=current_user.id,
        )
        db.add(job)
        created_jobs.append(job)

    await db.commit()
    for job in created_jobs:
        await db.refresh(job)

    queue_backend = await enqueue_parse_jobs([j.id for j in created_jobs], background_tasks)
    return BulkUploadResponse(
        batch_id=batch_id,
        jobs=[ParseJobItem.model_validate(j) for j in created_jobs],
        queue_backend=queue_backend,
        message=f"Queued {len(created_jobs)} resume{'s' if len(created_jobs) != 1 else ''} for parsing.",
    )


@router.get("/parse-jobs", response_model=List[ParseJobItem])
async def list_parse_jobs(
    batch_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """Poll bulk resume parse jobs, optionally filtered by `batch_id`."""
    stmt = select(ParseJob)
    if batch_id is not None:
        stmt = stmt.where(ParseJob.batch_id == batch_id)
    stmt = stmt.order_by(ParseJob.created_at.asc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [ParseJobItem.model_validate(r) for r in rows]


@router.get("/parse-jobs/{job_id}", response_model=ParseJobItem)
async def get_parse_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    row = (await db.execute(select(ParseJob).where(ParseJob.id == job_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parse job not found")
    return ParseJobItem.model_validate(row)


@router.get("/pending", response_model=List[PendingResumeItem])
async def list_pending_resumes(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    """List uploaded resume files that are saved in storage but not yet attached to a candidate."""
    res = await db.execute(
        select(ResumeFile)
        .where(ResumeFile.status == ResumeFileStatus.pending.value)
        .order_by(ResumeFile.created_at.desc())
        .limit(50)
    )
    return list(res.scalars().all())


@router.get("/{resume_file_id}/file")
async def stream_resume_file(
    resume_file_id: UUID,
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*READ_ROLES)),
):
    """Stream an uploaded resume file through the configured storage layer (authenticated + audited)."""
    res = await db.execute(select(ResumeFile).where(ResumeFile.id == resume_file_id))
    rf = res.scalar_one_or_none()
    if not rf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume file not found")

    try:
        file_bytes = await storage.read_file(rf.stored_filename)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored resume file is missing")

    await record_audit(
        db,
        user_id=current_user.id,
        action="export" if download else "view",
        entity="resume_file",
        entity_id=rf.id,
        metadata={"filename": rf.original_filename, "download": download},
    )

    safe_name = Path(rf.original_filename).name.replace('"', "")
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type=rf.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'{disposition}; filename="{safe_name}"'},
    )


@router.delete("/{resume_file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pending_resume(
    resume_file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Delete an unattached pending resume file from storage and database."""
    rf = (
        await db.execute(select(ResumeFile).where(ResumeFile.id == resume_file_id))
    ).scalar_one_or_none()
    if not rf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume file not found")

    attached_count = (
        await db.execute(
            select(func.count()).select_from(Candidate).where(Candidate.resume_file_id == rf.id)
        )
    ).scalar_one()
    if attached_count > 0 or rf.status == ResumeFileStatus.attached.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a resume attached to a saved candidate. Delete the candidate instead.",
        )

    stored_name = rf.stored_filename
    await db.delete(rf)
    await db.commit()
    await storage.delete_file(stored_name)

    await record_audit(
        db,
        user_id=current_user.id,
        action="delete",
        entity="resume_file",
        entity_id=resume_file_id,
        metadata={"reason": "pending_discard"},
    )
    return None


@router.post("/cleanup", response_model=dict)
async def trigger_orphan_cleanup(
    max_age_hours: int = Query(default=24, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    """Admin-only: immediately purge pending resume files older than `max_age_hours`."""
    deleted = await cleanup_orphan_resumes(db, max_age_hours=max_age_hours)
    return {"deleted": deleted, "max_age_hours": max_age_hours}


@router.get("/inbound-logs", response_model=List[InboundEmailLogResponse])
async def get_inbound_email_logs_endpoint(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    """List recent email-to-inbox CV ingestion events (domain-only, no PII)."""
    return await list_inbound_email_logs(db, limit=limit)


@router.post(
    "/inbound-email",
    response_model=InboundEmailLogResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_inbound_email_resumes(
    payload: InboundEmailWebhookPayload,
    background_tasks: BackgroundTasks,
    x_inbound_webhook_secret: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Email-to-inbox CV ingestion webhook (for Mailgun / Postmark / n8n / IMAP forwarders).
    Authenticates via `X-Inbound-Webhook-Secret` matching `INBOUND_EMAIL_WEBHOOK_SECRET`
    OR an `admin`/`recruiter` Bearer JWT. Deduplicates by `message_id` and queues PDF/DOCX
    attachments into the bulk review queue (`parse_jobs`).
    """
    actor_id: Optional[UUID] = None
    configured_secret = (settings.INBOUND_EMAIL_WEBHOOK_SECRET or "").strip()
    secret_ok = bool(
        configured_secret
        and x_inbound_webhook_secret
        and hmac.compare_digest(x_inbound_webhook_secret.strip(), configured_secret)
    )
    if not secret_ok:
        if authorization and authorization.lower().startswith("bearer "):
            token_str = authorization.split(" ", 1)[1].strip()
            try:
                claims = decode_access_token(token_str)
                if not claims or not claims.get("sub"):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid inbound webhook secret or bearer token",
                    )
                uid = UUID(str(claims.get("sub")))
                user = await get_user_by_id(db, uid)
                if not user or not user.is_active or user.role not in WRITE_ROLES:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
                actor_id = user.id
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid inbound webhook secret or bearer token",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing valid X-Inbound-Webhook-Secret or Bearer token",
            )

    msg_id = payload.message_id.strip()[:255]
    existing = (
        await db.execute(select(InboundEmailLog).where(InboundEmailLog.message_id == msg_id))
    ).scalar_one_or_none()
    if existing:
        return InboundEmailLogResponse.model_validate(existing)

    raw_from = (payload.from_email or "").strip()
    from_domain = (raw_from.split("@")[-1].lower()[:120] if "@" in raw_from else "unknown") or "unknown"

    batch_id = uuid.uuid4()
    created_jobs: List[ParseJob] = []

    for att in payload.attachments[: settings.BULK_UPLOAD_MAX_FILES]:
        ext = os.path.splitext(att.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        try:
            file_bytes = base64.b64decode(att.content_base64, validate=True)
        except Exception:
            continue
        if not file_bytes or len(file_bytes) > MAX_FILE_SIZE:
            continue

        file_meta = await storage.save_file(
            file_bytes=file_bytes,
            original_filename=att.filename,
            content_type=att.content_type or "application/octet-stream",
        )
        rf = ResumeFile(
            original_filename=file_meta["original_filename"],
            stored_filename=file_meta["stored_filename"],
            file_path=file_meta["file_path"],
            file_size=file_meta["file_size"],
            content_type=file_meta["content_type"],
            status=ResumeFileStatus.pending.value,
        )
        db.add(rf)
        await db.flush()

        job = ParseJob(
            batch_id=batch_id,
            resume_file_id=rf.id,
            original_filename=rf.original_filename,
            status=ParseJobStatus.queued.value,
            created_by=actor_id,
        )
        db.add(job)
        created_jobs.append(job)

    log_entry = InboundEmailLog(
        message_id=msg_id,
        from_domain=from_domain,
        subject=(payload.subject or "").strip()[:255],
        attachment_count=len(created_jobs),
        parse_batch_id=batch_id if created_jobs else None,
        status="processed" if created_jobs else "ignored",
        error=None if created_jobs else "No valid PDF/DOCX attachments found",
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    if created_jobs:
        await enqueue_parse_jobs([j.id for j in created_jobs], background_tasks)

    return InboundEmailLogResponse.model_validate(log_entry)
