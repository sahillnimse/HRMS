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


_BLIND_IDENTITY_KEYS = frozenset(
    {
        "full_name",
        "email",
        "phone",
        "phone_normalized",
        "linkedin_url",
        "github_url",
        "portfolio_url",
        "photo",
        "photo_url",
        "avatar",
        "institution",
        "college",
        "university",
    }
)


def blind_candidate_label(candidate_id: str | UUID) -> str:
    """Deterministic anonymized identifier for blind screening."""
    short = str(candidate_id).replace("-", "")[:6].upper()
    return f"Candidate #{short}"


def _mask_tokens_in_text(text_val: str, tokens: list[str]) -> str:
    masked = text_val or ""
    for tok in tokens:
        clean = (tok or "").strip()
        if len(clean) >= 3:
            masked = re.sub(re.escape(clean), "[Redacted]", masked, flags=re.IGNORECASE)
    return masked


def _sanitize_raw_for_blind(value: Any, tokens: list[str]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k in _BLIND_IDENTITY_KEYS or k in _INTERNAL_ONLY_KEYS:
                continue
            out[k] = _sanitize_raw_for_blind(v, tokens)
        return out
    if isinstance(value, list):
        return [_sanitize_raw_for_blind(item, tokens) for item in value]
    if isinstance(value, str):
        return _mask_tokens_in_text(value, tokens)
    return value


def redact_for_blind_screening(resp: CandidateResponse) -> CandidateResponse:
    """
    Anonymize a CandidateResponse for blind screening:
    hides full name, email, phone, social URLs, photo/avatar metadata, and college/institution names.
    """
    tokens: list[str] = []
    if resp.full_name:
        tokens.append(resp.full_name)
        for part in resp.full_name.split():
            if len(part) >= 3:
                tokens.append(part)
    if resp.email:
        tokens.append(resp.email)
    if resp.phone:
        tokens.append(resp.phone)

    redacted_edu = []
    for item in resp.education or []:
        if isinstance(item, dict):
            inst = str(item.get("institution") or "").strip()
            if inst:
                tokens.append(inst)
            copy = dict(item)
            copy["institution"] = "[Institution Redacted]"
            redacted_edu.append(copy)
        else:
            redacted_edu.append(item)

    redacted_work = []
    for item in resp.work_experience or []:
        if isinstance(item, dict):
            copy = dict(item)
            if isinstance(copy.get("bullets"), list):
                copy["bullets"] = [
                    _mask_tokens_in_text(b, tokens) if isinstance(b, str) else b
                    for b in copy["bullets"]
                ]
            redacted_work.append(copy)
        else:
            redacted_work.append(item)

    return resp.model_copy(
        update={
            "full_name": blind_candidate_label(resp.id),
            "email": None,
            "phone": None,
            "phone_normalized": None,
            "linkedin_url": None,
            "github_url": None,
            "portfolio_url": None,
            "profile_summary": _mask_tokens_in_text(resp.profile_summary, tokens),
            "work_experience": redacted_work,
            "education": redacted_edu,
            "raw_parsed_data": _sanitize_raw_for_blind(resp.raw_parsed_data or {}, tokens),
        }
    )
