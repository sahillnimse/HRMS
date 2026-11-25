"""Orphan resume file cleanup (pending files older than configured TTL)."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.candidate import Candidate, ResumeFile, ResumeFileStatus
from app.services.file_storage import BaseStorage, storage as default_storage

logger = logging.getLogger(__name__)


async def cleanup_orphan_resumes(
    db: AsyncSession,
    *,
    storage_backend: Optional[BaseStorage] = None,
    max_age_hours: Optional[int] = None,
) -> int:
    """
    Delete `resume_files` rows that are still `pending`, older than `max_age_hours`,
    and not referenced by any Candidate, along with their stored files.
    Returns the number of cleaned-up files.
    """
    store = storage_backend or default_storage
    hours = settings.ORPHAN_MAX_AGE_HOURS if max_age_hours is None else max_age_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    attached_ids = select(Candidate.resume_file_id).where(Candidate.resume_file_id.is_not(None))
    stmt = select(ResumeFile).where(
        ResumeFile.status == ResumeFileStatus.pending.value,
        ResumeFile.created_at < cutoff,
        ResumeFile.id.not_in(attached_ids),
    )

    result = await db.execute(stmt)
    orphans = list(result.scalars().all())
    if not orphans:
        return 0

    removed = 0
    for rf in orphans:
        try:
            await store.delete_file(rf.stored_filename)
        except Exception:
            logger.warning("Failed deleting orphan file from storage: %s", rf.stored_filename, exc_info=True)
        await db.delete(rf)
        removed += 1

    await db.commit()
    logger.info("Cleaned up %d orphan pending resume file(s).", removed)
    return removed


async def orphan_cleanup_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_minutes: Optional[int] = None,
    max_age_hours: Optional[int] = None,
) -> None:
    """Periodic background loop run inside FastAPI lifespan."""
    interval_seconds = max(60, (interval_minutes or settings.ORPHAN_CLEANUP_INTERVAL_MINUTES) * 60)
    while True:
        try:
            async with session_factory() as db:
                await cleanup_orphan_resumes(db, max_age_hours=max_age_hours)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error during scheduled orphan resume cleanup")
        await asyncio.sleep(interval_seconds)
