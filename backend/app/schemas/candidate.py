"""
Pydantic v2 schemas for Candidate API request/response.

Mirrors the SQLAlchemy Candidate model and the ParsedResume Gemini schema so
the frontend stays end-to-end type-safe.
"""

from datetime import datetime
from typing import List, Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, EmailStr


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
    technical_skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    hobbies_interests: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)

    raw_parsed_data: dict = Field(default_factory=dict)


class CandidateUpdate(BaseModel):
    """Partial update payload for editing a saved candidate."""

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
    technical_skills: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    soft_skills: Optional[List[str]] = None
    hobbies_interests: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    raw_parsed_data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CandidateResponse(BaseModel):
    """Full candidate profile returned after save or fetch."""

    id: UUID
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    profile_summary: str
    years_experience: float
    primary_domain: str
    work_experience: List[Any]
    education: List[Any]
    technical_skills: List[str]
    tools: List[str]
    soft_skills: List[str]
    hobbies_interests: List[str]
    languages: List[str]
    certifications: List[str]
    raw_parsed_data: dict
    resume_file_id: Optional[UUID] = None
    is_duplicate_flagged: bool
    created_at: datetime
    updated_at: datetime

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
    created_at: datetime
    current_title: Optional[str] = None
    current_company: Optional[str] = None

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
# Upload / parse responses
# ---------------------------------------------------------------------------

class DuplicateInfo(BaseModel):
    is_duplicate: bool
    candidate_id: Optional[UUID] = None
    matched_field: Optional[str] = None  # "email" | "phone" | None


class ResumeUploadResponse(BaseModel):
    """Response from POST /api/resumes/upload."""

    resume_file_id: UUID
    parsed_data: dict  # ParsedResume.to_flat_dict()
    duplicate: DuplicateInfo
    message: str
