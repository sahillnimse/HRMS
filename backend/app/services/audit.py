"""Audit logging helpers and viewer CTC/free-text redaction."""

import re
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import AuditLog
from app.models.user import UserRole
from app.schemas.candidate import CandidateResponse

_CTC_KEYS = frozenset({"current_ctc", "expected_ctc", "ctc_currency"})
_INTERNAL_ONLY_KEYS = frozenset({"_resume_text"})

# Patterns matching salary / CTC expressions written in free text
_FREE_TEXT_CTC_PATTERNS = (
    # Labeled CTC / salary / compensation / package phrases
    re.compile(
        r"(?i)\b(?:current|expected|present|last|annual|desired)?\s*"
        r"(?:ctc|salary|compensation|package)\s*(?:is|of|:|-|–|=)?\s*"
        r"(?:(?:inr|rs\.?|usd|eur|gbp|₹|\$|€|£)\s*)?"
        r"\d[\d,]*(?:\.\d+)?\s*(?:lpa|lakhs?|lacs?|k|m|cr|crores?|per\s+annum|p\.?a\.?|/\s*yr|/\s*year)?",
    ),
    # Currency + LPA / per annum figures without label
    re.compile(
        r"(?i)(?:inr|rs\.?|₹)\s*\d[\d,]*(?:\.\d+)?\s*(?:lpa|lakhs?|lacs?|crores?|cr|per\s+annum|p\.?a\.?)?"
        r"|\b\d+(?:\.\d+)?\s*lpa\b",
    ),
    # USD/EUR/GBP annual figures (e.g. $120,000, $150k/yr)
    re.compile(
        r"(?i)(?:\$|€|£|usd\s*|eur\s*|gbp\s*)\d{2,3}(?:,\d{3})+(?:\.\d+)?(?:\s*(?:per\s+year|/\s*yr|p\.?a\.?))?"
        r"|(?:\$|€|£)\d{2,3}k(?:\s*(?:/\s*yr|per\s+year))?\b",
    ),
)


def _redact_ctc_text(text: str) -> str:
    redacted = text
    for pattern in _FREE_TEXT_CTC_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _sanitize_raw_for_viewer(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k in _CTC_KEYS or k in _INTERNAL_ONLY_KEYS:
                continue
            out[k] = _sanitize_raw_for_viewer(v)
        return out
    if isinstance(value, list):
        return [_sanitize_raw_for_viewer(item) for item in value]
    if isinstance(value, str):
        return _redact_ctc_text(value)
    return value


def _strip_resume_text_only(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_resume_text_only(v) for k, v in value.items() if k not in _INTERNAL_ONLY_KEYS}
    if isinstance(value, list):
        return [_strip_resume_text_only(item) for item in value]
    return value


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
    Always strip `_resume_text` from responses. For `viewer`, also strip all CTC
    fields (top-level and nested in `raw_parsed_data`) and redact salary/CTC
    mentions from free-text fields (`profile_summary`, work bullets, raw text).
    """
    if role in (UserRole.admin, UserRole.recruiter):
        return resp.model_copy(
            update={"raw_parsed_data": _strip_resume_text_only(resp.raw_parsed_data or {})}
        )

    cleaned_work = []
    for item in resp.work_experience or []:
        if isinstance(item, dict):
            copy = dict(item)
            if isinstance(copy.get("bullets"), list):
                copy["bullets"] = [
                    _redact_ctc_text(b) if isinstance(b, str) else b for b in copy["bullets"]
                ]
            cleaned_work.append(copy)
        else:
            cleaned_work.append(item)

    return resp.model_copy(
        update={
            "current_ctc": None,
            "expected_ctc": None,
            "ctc_currency": None,
            "profile_summary": _redact_ctc_text(resp.profile_summary),
            "work_experience": cleaned_work,
            "raw_parsed_data": _sanitize_raw_for_viewer(resp.raw_parsed_data or {}),
        }
    )
