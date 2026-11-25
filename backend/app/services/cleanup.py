"""Orphan resume file cleanup and Phase 3 candidate data retention purge."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.crud.candidate import delete_candidate
from app.models.candidate import Candidate, ResumeFile, ResumeFileStatus
from app.services.audit import record_audit
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


async def purge_expired_candidates(
    db: AsyncSession,
    *,
    retention_days: Optional[int] = None,
    storage_backend: Optional[BaseStorage] = None,
    actor_id: Optional[UUID] = None,
    dry_run: bool = False,
) -> Tuple[int, List[UUID]]:
    """
    Delete candidates whose consent/creation timestamp is older than `retention_days`.
    Removes both DB rows (including `raw_parsed_data._resume_text`) and physical resume
    files, while writing a PII-free audit trail entry for each purged candidate.
    """
    days = settings.RETENTION_DAYS if retention_days is None else retention_days
    if days <= 0:
        return 0, []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    reference_ts = func.coalesce(Candidate.consent_given_at, Candidate.created_at)
    stmt = select(Candidate.id).where(reference_ts < cutoff)
    expired_ids = list((await db.execute(stmt)).scalars().all())
    if not expired_ids or dry_run:
        return len(expired_ids), expired_ids

    purged: List[UUID] = []
    for cid in expired_ids:
        deleted = await delete_candidate(db, cid, storage_backend=storage_backend)
        if deleted:
            await record_audit(
                db,
                user_id=actor_id,
                action="retention_purge",
                entity="candidate",
                entity_id=cid,
                metadata={"retention_days": days, "reason": "retention_policy"},
            )
            purged.append(cid)

    logger.info("Purged %d candidate(s) exceeding %d-day retention policy.", len(purged), days)
    return len(purged), purged


async def orphan_cleanup_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_minutes: Optional[int] = None,
    max_age_hours: Optional[int] = None,
) -> None:
    """Periodic background loop run inside FastAPI lifespan for orphan cleanup & data retention."""
    interval_seconds = max(60, (interval_minutes or settings.ORPHAN_CLEANUP_INTERVAL_MINUTES) * 60)
    while True:
        try:
            async with session_factory() as db:
                await cleanup_orphan_resumes(db, max_age_hours=max_age_hours)
                if settings.RETENTION_DAYS > 0:
                    await purge_expired_candidates(db, retention_days=settings.RETENTION_DAYS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error during scheduled cleanup/retention sweep")
        await asyncio.sleep(interval_seconds)
