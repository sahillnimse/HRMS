"""Pydantic v2 schemas for Jobs, Applications, Notes, Activity Timeline, and Audit Logs."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.pipeline import ApplicationStage, JobStatus


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class JobCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    department: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=255)
    description: str = Field(default="")
    required_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    min_years: Optional[float] = Field(None, ge=0)
    max_years: Optional[float] = Field(None, ge=0)
    status: JobStatus = JobStatus.open


class JobUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    department: Optional[str] = Field(None, max_length=120)
    location: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    required_skills: Optional[List[str]] = None
    nice_to_have_skills: Optional[List[str]] = None
    min_years: Optional[float] = Field(None, ge=0)
    max_years: Optional[float] = Field(None, ge=0)
    status: Optional[JobStatus] = None


class JobResponse(BaseModel):
    id: UUID
    title: str
    department: str
    location: str
    description: str
    required_skills: List[str]
    nice_to_have_skills: List[str]
    min_years: Optional[float] = None
    max_years: Optional[float] = None
    status: JobStatus
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    application_count: int = 0
    stage_counts: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Applications & Events
# ---------------------------------------------------------------------------

class ApplicationCreate(BaseModel):
    candidate_id: UUID
    job_id: UUID
    stage: ApplicationStage = ApplicationStage.applied


class ApplicationStageUpdate(BaseModel):
    stage: ApplicationStage
    rejection_reason: Optional[str] = None
    reason: Optional[str] = None


class ApplicationEventResponse(BaseModel):
    id: UUID
    application_id: UUID
    from_stage: Optional[str] = None
    to_stage: str
    changed_by: Optional[UUID] = None
    actor_name: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationCardCandidate(BaseModel):
    id: UUID
    full_name: str
    email: Optional[str] = None
    city: Optional[str] = None
    primary_domain: str
    years_experience: float
    technical_skills: List[str]
    notice_period_days: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ApplicationResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    job_id: UUID
    stage: ApplicationStage
    stage_changed_at: datetime
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    candidate: Optional[ApplicationCardCandidate] = None
    job_title: Optional[str] = None
    job_department: Optional[str] = None
    job_status: Optional[JobStatus] = None

    model_config = ConfigDict(from_attributes=True)


class JobDetailResponse(JobResponse):
    applications: List[ApplicationResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Candidate Notes
# ---------------------------------------------------------------------------

class CandidateNoteCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    tags: List[str] = Field(default_factory=list)


class CandidateNoteResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    author_id: Optional[UUID] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    body: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Audit Logs & Activity Timeline
# ---------------------------------------------------------------------------

class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    entity: str
    entity_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityTimelineItem(BaseModel):
    id: str
    kind: str  # "stage_change" | "note" | "audit"
    action: str
    summary: str
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
