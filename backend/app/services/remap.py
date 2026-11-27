"""
Admin-only re-mapping utility for existing Candidate records.

Re-derives:
  - work_experience[].employment_type (word-boundary safe deterministic inference)
  - education[] start_year / end_year / graduation_year / is_current (from stored resume text/file)
  - projects[] (from stored resume text/file when currently empty)

Safety guarantees:
  - dry_run=True by default (no writes unless explicitly requested).
  - Inspects `audit_logs` (`action='edit'`, `entity='candidate'`) and NEVER overwrites
    a section (`education`, `work_experience`, or `projects`) that a user previously
    edited by hand via the API.
  - Never logs CV text or candidate PII.
"""

import logging
from typing import List, Optional, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.candidate import Candidate
from app.models.pipeline import AuditLog
from app.schemas.candidate import SectionRemapCandidateResult, SectionRemapResponse
from app.services.audit import record_audit
from app.services.file_storage import BaseStorage, storage as default_storage
from app.services.section_mapping import (
    extract_education_dates_from_text,
    extract_projects_from_text,
    normalize_education_list,
    normalize_projects_list,
    normalize_work_experience_list,
)
from app.services.text_extraction import extract_text_with_meta

logger = logging.getLogger(__name__)


async def _get_hand_edited_fields(db: AsyncSession, candidate_id: UUID) -> Set[str]:
    """Return set of candidate fields previously modified via manual edit audit logs."""
    rows = (
        await db.execute(
            select(AuditLog.details).where(
                AuditLog.entity == "candidate",
                AuditLog.entity_id == str(candidate_id),
                AuditLog.action == "edit",
            )
        )
    ).scalars().all()
    edited: Set[str] = set()
    for details in rows:
        if isinstance(details, dict):
            fields = details.get("updated_fields")
            if isinstance(fields, list):
                for f in fields:
                    if isinstance(f, str):
                        edited.add(f)
    return edited


async def _load_resume_text_for_candidate(
    candidate: Candidate,
    *,
    storage_backend: BaseStorage,
) -> tuple[str, str]:
    """
    Retrieve resume text from `raw_parsed_data["_resume_text"]` if present,
    otherwise read and extract text from the attached `ResumeFile`.
    Returns `(text, source_label)`.
    """
    if isinstance(candidate.raw_parsed_data, dict):
        stored_text = candidate.raw_parsed_data.get("_resume_text")
        if isinstance(stored_text, str) and len(stored_text.strip()) >= 20:
            return stored_text, "resume_text"

    rf = candidate.resume_file
    if rf is not None and rf.stored_filename:
        try:
            file_bytes = await storage_backend.read_file(rf.stored_filename)
            extracted, _ = await extract_text_with_meta(file_bytes, rf.content_type or "")
            if extracted and len(extracted.strip()) >= 20:
                return extracted, "resume_file"
        except Exception:
            logger.warning(
                "Could not extract text from stored resume for candidate %s",
                candidate.id,
            )

    return "", "existing_fields_only"


async def remap_candidate_sections(
    db: AsyncSession,
    *,
    dry_run: bool = True,
    candidate_id: Optional[UUID] = None,
    limit: int = 100,
    actor_id: Optional[UUID] = None,
    storage_backend: Optional[BaseStorage] = None,
) -> SectionRemapResponse:
    """Re-map education dates, work employment_type, and projects for existing candidates."""
    store = storage_backend or default_storage
    stmt = (
        select(Candidate)
        .options(selectinload(Candidate.resume_file))
        .order_by(Candidate.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    if candidate_id is not None:
        stmt = stmt.where(Candidate.id == candidate_id)

    candidates = list((await db.execute(stmt)).scalars().all())
    results: List[SectionRemapCandidateResult] = []
    would_update = 0
    updated_count = 0
    skipped_hand_edited_total = 0

    for cand in candidates:
        hand_edited = await _get_hand_edited_fields(db, cand.id)
        resume_text, source_used = await _load_resume_text_for_candidate(
            cand, storage_backend=store
        )

        changed_fields: List[str] = []
        skipped_fields: List[str] = []

        # 1. Work experience employment_type
        if "work_experience" in hand_edited:
            skipped_fields.append("work_experience")
        else:
            new_work = normalize_work_experience_list(cand.work_experience or [])
            if new_work != (cand.work_experience or []):
                changed_fields.append("work_experience")
                if not dry_run:
                    cand.work_experience = new_work

        # 2. Education start/end/graduation years
        if "education" in hand_edited:
            skipped_fields.append("education")
        else:
            new_edu = (
                extract_education_dates_from_text(resume_text, cand.education or [])
                if resume_text
                else normalize_education_list(cand.education or [])
            )
            if new_edu != (cand.education or []):
                changed_fields.append("education")
                if not dry_run:
                    cand.education = new_edu

        # 3. Projects (only populate if currently empty and not hand-edited)
        if "projects" in hand_edited:
            skipped_fields.append("projects")
        else:
            existing_projects = cand.projects or []
            if not existing_projects and resume_text:
                extracted_projects = extract_projects_from_text(resume_text)
                if extracted_projects:
                    changed_fields.append("projects")
                    if not dry_run:
                        cand.projects = extracted_projects
            elif existing_projects:
                norm_proj = normalize_projects_list(existing_projects)
                if norm_proj != existing_projects:
                    changed_fields.append("projects")
                    if not dry_run:
                        cand.projects = norm_proj

        if skipped_fields:
            skipped_hand_edited_total += 1
        if changed_fields:
            would_update += 1
            if not dry_run:
                updated_count += 1
                await record_audit(
                    db,
                    user_id=actor_id,
                    action="section_remap",
                    entity="candidate",
                    entity_id=cand.id,
                    metadata={
                        "updated_fields": changed_fields,
                        "source_used": source_used,
                    },
                    commit=False,
                )

        results.append(
            SectionRemapCandidateResult(
                candidate_id=cand.id,
                source_used=source_used,
                updated_fields=changed_fields,
                skipped_hand_edited_fields=skipped_fields,
            )
        )

    if not dry_run and updated_count > 0:
        await db.commit()

    return SectionRemapResponse(
        dry_run=dry_run,
        scanned=len(candidates),
        would_update=would_update,
        updated=updated_count,
        skipped_hand_edited=skipped_hand_edited_total,
        results=results,
    )
