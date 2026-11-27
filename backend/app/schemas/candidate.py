"""
Pydantic v2 schemas for Candidate API request/response.

Mirrors the SQLAlchemy Candidate model and the ParsedResume schema so
the frontend stays end-to-end type-safe.
"""

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _strip_internal_resume_text(value: Any) -> Any:
    """Recursively strip `_resume_text` from dicts before serializing API responses."""
    if isinstance(value, dict):
        return {
            k: _strip_internal_resume_text(v)
            for k, v in value.items()
            if k != "_resume_text"
        }
    if isinstance(value, list):
        return [_strip_internal_resume_text(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CandidateCreate(BaseModel):
    """Payload sent from the Review UI when HR clicks 'Save Candidate'."""

    resume_file_id: Optional[UUID] = None

    # Contact
    full_name: str = Field(..., min_length=1)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None

    # Profile
    profile_summary: str = Field(..., min_length=1)
    years_experience: float = Field(..., ge=0)
    primary_domain: str = Field(..., min_length=1)

    # JSONB arrays / objects
    work_experience: List[Any] = Field(default_factory=list)
    education: List[Any] = Field(default_factory=list)
    projects: List[Any] = Field(default_factory=list)
    technical_skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    hobbies_interests: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)

    # Compensation & mobility
    notice_period_days: Optional[int] = Field(None, ge=0)
    current_ctc: Optional[float] = Field(None, ge=0)
    expected_ctc: Optional[float] = Field(None, ge=0)
    ctc_currency: Optional[str] = Field(None, max_length=10)
    preferred_locations: List[str] = Field(default_factory=list)
    open_to_relocate: Optional[bool] = None

    # Privacy, consent & provenance (Phase 3)
    consent_given_at: Optional[datetime] = None
    source: str = Field(default="upload", max_length=80)

    raw_parsed_data: dict = Field(default_factory=dict)

    # Duplicate resolution controls
    allow_duplicate: bool = False
    is_duplicate_flagged: bool = False


class CandidateUpdate(BaseModel):
    """Partial update payload for editing or updating an existing candidate."""

    resume_file_id: Optional[UUID] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    profile_summary: Optional[str] = None
    years_experience: Optional[float] = Field(None, ge=0)
    primary_domain: Optional[str] = None
    work_experience: Optional[List[Any]] = None
    education: Optional[List[Any]] = None
    projects: Optional[List[Any]] = None
    technical_skills: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    soft_skills: Optional[List[str]] = None
    hobbies_interests: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    notice_period_days: Optional[int] = Field(None, ge=0)
    current_ctc: Optional[float] = Field(None, ge=0)
    expected_ctc: Optional[float] = Field(None, ge=0)
    ctc_currency: Optional[str] = Field(None, max_length=10)
    preferred_locations: Optional[List[str]] = None
    open_to_relocate: Optional[bool] = None
    consent_given_at: Optional[datetime] = None
    source: Optional[str] = Field(None, max_length=80)
    raw_parsed_data: Optional[dict] = None
    is_duplicate_flagged: Optional[bool] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CandidateResponse(BaseModel):
    """Full candidate profile returned after save or fetch."""

    id: UUID
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_normalized: Optional[str] = None
    city: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    profile_summary: str
    years_experience: float
    primary_domain: str
    work_experience: List[Any]
    education: List[Any]
    projects: List[Any] = Field(default_factory=list)
    technical_skills: List[str]
    tools: List[str]
    soft_skills: List[str]
    hobbies_interests: List[str]
    languages: List[str]
    certifications: List[str]
    notice_period_days: Optional[int] = None
    current_ctc: Optional[float] = None
    expected_ctc: Optional[float] = None
    ctc_currency: Optional[str] = None
    preferred_locations: List[str] = Field(default_factory=list)
    open_to_relocate: Optional[bool] = None
    consent_given_at: Optional[datetime] = None
    source: str = "upload"
    raw_parsed_data: dict
    resume_file_id: Optional[UUID] = None
    is_duplicate_flagged: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("raw_parsed_data", mode="before")
    @classmethod
    def strip_resume_text(cls, v: Any) -> dict:
        if not isinstance(v, dict):
            return {}
        return _strip_internal_resume_text(v)

    model_config = ConfigDict(from_attributes=True)


class CandidateListItem(BaseModel):
    """Lightweight candidate row for the dashboard table."""

    id: UUID
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    primary_domain: str
    years_experience: float
    technical_skills: List[str]
    is_duplicate_flagged: bool = False
    resume_file_id: Optional[UUID] = None
    resume_filename: Optional[str] = None
    source: str = "upload"
    consent_given_at: Optional[datetime] = None
    created_at: datetime
    current_title: Optional[str] = None
    current_company: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PendingResumeItem(BaseModel):
    """Uploaded resume file not yet attached to a saved candidate."""

    id: UUID
    original_filename: str
    file_size: int
    content_type: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NamedCount(BaseModel):
    name: str
    count: int


class CandidateStats(BaseModel):
    """Aggregate talent-pool metrics for the dashboard."""

    total: int
    avg_years_experience: float
    added_this_week: int
    domains: List[NamedCount]
    top_skills: List[NamedCount]


# ---------------------------------------------------------------------------
# Upload / parse / duplicate responses
# ---------------------------------------------------------------------------

class DuplicateMatch(BaseModel):
    candidate_id: UUID
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    primary_domain: str
    matched_fields: List[str] = Field(default_factory=list)
    name_similarity: Optional[float] = None


class DuplicateInfo(BaseModel):
    is_duplicate: bool
    candidate_id: Optional[UUID] = None
    matched_field: Optional[str] = None
    matches: List[DuplicateMatch] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    """Response from POST /api/v1/resumes/upload."""

    resume_file_id: UUID
    parsed_data: dict  # ParsedResume.to_flat_dict() without _resume_text
    duplicate: DuplicateInfo
    ocr_used: bool = False
    message: str

    @field_validator("parsed_data", mode="before")
    @classmethod
    def strip_resume_text_from_upload(cls, v: Any) -> dict:
        if not isinstance(v, dict):
            return {}
        return _strip_internal_resume_text(v)


class ParseJobItem(BaseModel):
    """Status and parsed payload for a single file inside a bulk upload batch."""

    id: UUID
    batch_id: UUID
    resume_file_id: Optional[UUID] = None
    original_filename: str
    status: str
    result_json: Optional[dict] = None
    duplicate_json: Optional[dict] = None
    error_message: Optional[str] = None
    ocr_used: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    @field_validator("result_json", mode="before")
    @classmethod
    def strip_resume_text_from_job(cls, v: Any) -> Optional[dict]:
        if v is None:
            return None
        if not isinstance(v, dict):
            return {}
        return _strip_internal_resume_text(v)

    model_config = ConfigDict(from_attributes=True)


class BulkUploadResponse(BaseModel):
    """Response from POST /api/v1/resumes/bulk-upload."""

    batch_id: UUID
    jobs: List[ParseJobItem]
    queue_backend: str
    message: str


class RetentionPurgeResponse(BaseModel):
    """Response from POST /api/v1/privacy/purge-expired."""

    retention_days: int
    dry_run: bool
    matched_count: int
    purged_count: int
    candidate_ids: List[UUID] = Field(default_factory=list)


class SectionRemapCandidateResult(BaseModel):
    candidate_id: UUID
    source_used: str  # "resume_text" | "resume_file" | "existing_fields_only"
    updated_fields: List[str] = Field(default_factory=list)
    skipped_hand_edited_fields: List[str] = Field(default_factory=list)


class SectionRemapResponse(BaseModel):
    """Response from POST /api/v1/candidates/admin/remap-sections."""

    dry_run: bool
    scanned: int
    would_update: int
    updated: int
    skipped_hand_edited: int
    results: List[SectionRemapCandidateResult] = Field(default_factory=list)
