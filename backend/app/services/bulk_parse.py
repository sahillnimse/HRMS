"""Phase 3 bulk resume parsing pipeline (ARQ/Redis when REDIS_URL is set, else FastAPI BackgroundTasks)."""

from datetime import datetime, timezone
import logging
from typing import Optional, Tuple
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.crud.candidate import find_duplicates
from app.db.session import AsyncSessionLocal
from app.models.candidate import ParseJob, ParseJobStatus, ResumeFile
from app.schemas.candidate import DuplicateInfo
from app.schemas.resume import ParsedResume
from app.services.experience import compute_years_experience
from app.services.file_storage import storage
from app.services.gemini_parser import GeminiParser
from app.services.text_extraction import extract_text_with_meta

logger = logging.getLogger(__name__)


async def parse_resume_pipeline(
    db: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    stored_filename: str,
    extract_fn=None,
    parser_cls=None,
) -> Tuple[dict, DuplicateInfo, bool]:
    """
    Shared parse pipeline: extract text (with OCR fallback for scanned PDFs),
    parse via Gemini/OpenRouter, deterministically calculate years_experience,
    and run multi-match duplicate detection.
    """
    if extract_fn is not None:
        extracted = await extract_fn(file_bytes, content_type)
        if isinstance(extracted, tuple):
            resume_text, ocr_used = extracted
        else:
            resume_text, ocr_used = extracted, False
    else:
        resume_text, ocr_used = await extract_text_with_meta(file_bytes, content_type)
    if not resume_text or len(resume_text.strip()) < 10:
        raise ValueError("Could not extract readable text from the resume.")

    parser = (parser_cls or GeminiParser)()
    parsed: ParsedResume = await parser.parse_resume(resume_text)
    flat = parsed.to_flat_dict()

    llm_years = flat["years_experience"]
    computed_years = compute_years_experience(flat["work_experience"])
    flat["years_experience"] = computed_years

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
    else:
        duplicate = DuplicateInfo(is_duplicate=False, matches=[])

    flat["raw_parsed_data"] = {
        **flat,
        "_llm_years_experience": llm_years,
        "_computed_years_experience": computed_years,
        "_source_filename": filename,
        "_stored_filename": stored_filename,
        "_ocr_used": ocr_used,
    }
    return flat, duplicate, ocr_used


async def process_parse_job(
    job_id: UUID,
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
) -> None:
    """Execute a single queued ParseJob and persist `done` or `failed` state."""
    factory = session_factory or AsyncSessionLocal
    async with factory() as db:
        job = (await db.execute(select(ParseJob).where(ParseJob.id == job_id))).scalar_one_or_none()
        if not job:
            return
        job.status = ParseJobStatus.processing.value
        await db.commit()

        try:
            if not job.resume_file_id:
                raise ValueError("Missing resume file reference")
            rf = (
                await db.execute(select(ResumeFile).where(ResumeFile.id == job.resume_file_id))
            ).scalar_one_or_none()
            if not rf:
                raise ValueError("Resume file record not found")

            file_bytes = await storage.read_file(rf.stored_filename)
            flat, duplicate, ocr_used = await parse_resume_pipeline(
                db,
                file_bytes=file_bytes,
                filename=rf.original_filename,
                content_type=rf.content_type,
                stored_filename=rf.stored_filename,
            )

            job.status = ParseJobStatus.done.value
            job.result_json = flat
            job.duplicate_json = duplicate.model_dump(mode="json")
            job.ocr_used = ocr_used
            job.error_message = None
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:
            logger.warning("Bulk parse job %s failed: %s", job_id, exc)
            job.status = ParseJobStatus.failed.value
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()


async def enqueue_parse_jobs(
    job_ids: list[UUID],
    background_tasks: BackgroundTasks,
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
) -> str:
    """
    Enqueue parse jobs via ARQ/Redis if REDIS_URL is configured and arq is installed;
    otherwise fall back seamlessly to FastAPI BackgroundTasks.
    """
    redis_url = (settings.REDIS_URL or "").strip()
    if redis_url:
        try:
            from arq import create_pool  # type: ignore[import-untyped]
            from arq.connections import RedisSettings  # type: ignore[import-untyped]

            pool = await create_pool(RedisSettings.from_dsn(redis_url))
            try:
                for jid in job_ids:
                    await pool.enqueue_job("process_parse_job", str(jid))
            finally:
                await pool.close()
            return "redis"
        except Exception:
            logger.warning("Redis/ARQ enqueue failed; falling back to BackgroundTasks", exc_info=True)

    for jid in job_ids:
        background_tasks.add_task(process_parse_job, jid, session_factory)
    return "background_tasks"
