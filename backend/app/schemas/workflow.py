"""Pydantic v2 schemas for Phase 5: Interviews, Scorecards, Emails, and Offers."""

from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.workflow import (
    EmailStatus,
    InterviewMode,
    InterviewStatus,
    OfferStatus,
    ScorecardRecommendation,
)


# ---------------------------------------------------------------------------
# Interviews & Participants
# ---------------------------------------------------------------------------

class InterviewParticipantOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    role: str


class InterviewCreate(BaseModel):
    round_name: str = Field(..., min_length=1, max_length=120)
    scheduled_at: datetime
    duration_minutes: int = Field(default=45, ge=10, le=480)
    mode: InterviewMode = InterviewMode.video
    location_or_link: str = Field(default="", max_length=512)
    participant_ids: List[UUID] = Field(default_factory=list)


class InterviewUpdate(BaseModel):
    round_name: Optional[str] = Field(None, min_length=1, max_length=120)
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=10, le=480)
    mode: Optional[InterviewMode] = None
    location_or_link: Optional[str] = Field(None, max_length=512)
    status: Optional[InterviewStatus] = None
    participant_ids: Optional[List[UUID]] = None


class ScorecardAggregate(BaseModel):
    count: int = 0
    average_rating: Optional[float] = None
    scale: int = 5
    recommendations: Dict[str, int] = Field(
        default_factory=lambda: {"strong_no": 0, "no": 0, "yes": 0, "strong_yes": 0}
    )


class InterviewResponse(BaseModel):
    id: UUID
    application_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: Optional[str] = None
    job_id: Optional[UUID] = None
    job_title: Optional[str] = None
    round_name: str
    scheduled_at: datetime
    duration_minutes: int
    mode: str
    location_or_link: str
    status: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    participants: List[InterviewParticipantOut] = Field(default_factory=list)
    scorecard_aggregate: ScorecardAggregate = Field(default_factory=ScorecardAggregate)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Scorecard Templates & Scorecards
# ---------------------------------------------------------------------------

class ScorecardCompetency(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    weight: float = Field(default=1.0, gt=0)


class ScorecardTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    competencies: List[ScorecardCompetency] = Field(..., min_length=1)
    scale: int = Field(default=5, ge=3, le=10)


class ScorecardTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    competencies: Optional[List[ScorecardCompetency]] = None
    scale: Optional[int] = Field(None, ge=3, le=10)


class ScorecardTemplateResponse(BaseModel):
    id: UUID
    name: str
    competencies: List[ScorecardCompetency]
    scale: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScorecardSubmit(BaseModel):
    template_id: Optional[UUID] = None
    ratings: Dict[str, float] = Field(default_factory=dict)
    recommendation: ScorecardRecommendation
    comments: str = Field(default="", max_length=5000)


class ScorecardItemResponse(BaseModel):
    id: UUID
    interview_id: UUID
    interviewer_id: UUID
    interviewer_name: Optional[str] = None
    interviewer_email: Optional[str] = None
    template_id: Optional[UUID] = None
    ratings: Dict[str, float]
    average_rating: Optional[float] = None
    recommendation: str
    comments: str
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InterviewScorecardsResponse(BaseModel):
    interview_id: UUID
    aggregate: ScorecardAggregate
    scorecards: List[ScorecardItemResponse] = Field(default_factory=list)
    peer_scorecards_locked: bool = False
    viewer_aggregate_only: bool = False
    my_submitted: bool = False


# ---------------------------------------------------------------------------
# Email Templates & Sending
# ---------------------------------------------------------------------------

class EmailTemplateCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    subject: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    stage_trigger: Optional[str] = Field(None, max_length=32)
    auto_send: bool = False


class EmailTemplateUpdate(BaseModel):
    subject: Optional[str] = Field(None, min_length=1, max_length=255)
    body: Optional[str] = Field(None, min_length=1)
    stage_trigger: Optional[str] = Field(None, max_length=32)
    auto_send: Optional[bool] = None


class EmailTemplateResponse(BaseModel):
    id: UUID
    key: str
    subject: str
    body: str
    stage_trigger: Optional[str] = None
    auto_send: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailPreviewRequest(BaseModel):
    candidate_id: UUID
    application_id: Optional[UUID] = None
    template_key: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    extra_vars: Dict[str, str] = Field(default_factory=dict)


class EmailPreviewResponse(BaseModel):
    to: Optional[str] = None
    subject: str
    body: str
    template_key: Optional[str] = None


class EmailSendRequest(BaseModel):
    candidate_id: UUID
    application_id: Optional[UUID] = None
    template_key: Optional[str] = None
    to: Optional[EmailStr] = None
    subject: Optional[str] = Field(None, max_length=255)
    body: Optional[str] = None
    extra_vars: Dict[str, str] = Field(default_factory=dict)
    confirm_rejection: bool = False


class EmailLogResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    application_id: Optional[UUID] = None
    template_key: Optional[str] = None
    to: str
    subject: str
    status: EmailStatus | str
    error: Optional[str] = None
    created_by: Optional[UUID] = None
    actor_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Offers
# ---------------------------------------------------------------------------

class OfferCreate(BaseModel):
    offered_ctc: float = Field(..., gt=0)
    currency: str = Field(default="INR", min_length=2, max_length=10)
    status: OfferStatus = OfferStatus.draft
    expected_joining_date: Optional[date] = None
    decline_reason: Optional[str] = None
    notes: str = Field(default="", max_length=3000)


class OfferUpdate(BaseModel):
    offered_ctc: Optional[float] = Field(None, gt=0)
    currency: Optional[str] = Field(None, min_length=2, max_length=10)
    status: Optional[OfferStatus] = None
    expected_joining_date: Optional[date] = None
    decline_reason: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=3000)


class OfferResponse(BaseModel):
    id: UUID
    application_id: UUID
    candidate_id: Optional[UUID] = None
    candidate_name: Optional[str] = None
    job_id: Optional[UUID] = None
    job_title: Optional[str] = None
    offered_ctc: float
    currency: str
    status: str
    expected_joining_date: Optional[date] = None
    decline_reason: Optional[str] = None
    notes: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
