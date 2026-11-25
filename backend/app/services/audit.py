"""Audit logging helpers and viewer CTC redaction."""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import AuditLog
from app.models.user import UserRole
from app.schemas.candidate import CandidateResponse

_CTC_KEYS = ("current_ctc", "expected_ctc", "ctc_currency")


async def record_audit(
    db: AsyncSession,
    *,
    user_id: Optional[UUID],
    action: str,
    entity: str,
    entity_id: str | UUID,
    metadata: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> AuditLog:
    """Append an immutable audit log record."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        details=metadata or {},
    )
    db.add(entry)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return entry


def redact_ctc_for_role(resp: CandidateResponse, role: UserRole) -> CandidateResponse:
    """
    Compensation (CTC) fields are visible to admin and recruiter only.
    Strip them (including inside raw_parsed_data) before returning to viewer.
    """
    if role in (UserRole.admin, UserRole.recruiter):
        return resp
    cleaned_raw = {k: v for k, v in (resp.raw_parsed_data or {}).items() if k not in _CTC_KEYS}
    return resp.model_copy(
        update={
            "current_ctc": None,
            "expected_ctc": None,
            "ctc_currency": None,
            "raw_parsed_data": cleaned_raw,
        }
    )
