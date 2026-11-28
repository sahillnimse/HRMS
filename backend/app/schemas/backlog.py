"""Pydantic v2 schemas for High-ROI Backlog features."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.matching import CandidateSearchItem


# --- 1. Interview Question Generator ---

class InterviewQuestionItem(BaseModel):
    category: Literal["technical", "project_deep_dive", "skill_gap", "verification", "behavioral"]
    target_topic: str
    question: str
    what_to_look_for: str


class InterviewQuestionsRequest(BaseModel):
    job_id: Optional[UUID] = None
    count: int = Field(default=6, ge=3, le=10)
    blind: bool = False


class InterviewQuestionsResponse(BaseModel):
    candidate_id: UUID
    job_id: Optional[UUID] = None
    job_title: Optional[str] = None
    model: str
    questions: List[InterviewQuestionItem] = Field(default_factory=list)


# --- 2. Natural-Language Search ---

class ParsedNLFilters(BaseModel):
    skills: List[str] = Field(default_factory=list)
    min_years: Optional[float] = None
    max_years: Optional[float] = None
    city: Optional[str] = None
    max_notice_days: Optional[int] = None
    primary_domain: Optional[str] = None
    semantic_query: str = ""


class NLSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=18, ge=1, le=50)
    blind: bool = False


class NLSearchResponse(BaseModel):
    original_query: str
    parser_mode: str  # "ai" | "deterministic"
    parsed_filters: ParsedNLFilters
    items: List[CandidateSearchItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    pages: int
    semantic_used: bool = False


# --- 3. Talent Pools & Silver-Medalist Resurfacing ---

class TalentPoolCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field(default="", max_length=400)
    color: str = Field(default="teal", max_length=32)


class TalentPoolResponse(BaseModel):
    id: UUID
    name: str
    description: str
    color: str
    member_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TalentPoolMemberAdd(BaseModel):
    candidate_id: UUID
    notes: str = Field(default="", max_length=300)


class TalentPoolMemberItem(BaseModel):
    pool_id: UUID
    candidate_id: UUID
    full_name: str
    primary_domain: str
    years_experience: float
    technical_skills: List[str] = Field(default_factory=list)
    notes: str = ""
    added_at: datetime


class ResurfacedCandidateItem(BaseModel):
    candidate_id: UUID
    full_name: str
    primary_domain: str
    years_experience: float
    past_job_id: UUID
    past_job_title: str
    past_highest_stage: str
    match_score: float
    matched_required_skills: List[str] = Field(default_factory=list)
    missing_required_skills: List[str] = Field(default_factory=list)
    why: str
    talent_pools: List[str] = Field(default_factory=list)


class ResurfaceResponse(BaseModel):
    job_id: UUID
    job_title: str
    total: int
    candidates: List[ResurfacedCandidateItem] = Field(default_factory=list)


# --- 4. Email-to-Inbox CV Ingestion ---

class InboundAttachmentPayload(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(default="application/pdf", max_length=120)
    content_base64: str = Field(..., min_length=4)


class InboundEmailWebhookPayload(BaseModel):
    message_id: str = Field(..., min_length=3, max_length=255)
    from_email: str = Field(default="unknown@example.com", max_length=255)
    subject: str = Field(default="", max_length=255)
    attachments: List[InboundAttachmentPayload] = Field(default_factory=list)


class InboundEmailLogResponse(BaseModel):
    id: UUID
    message_id: str
    from_domain: str
    subject: str
    attachment_count: int
    parse_batch_id: Optional[UUID] = None
    status: str
    error: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- 5. India DPDP Act Erasure & Consent Requests ---

class ErasureRequestCreate(BaseModel):
    candidate_id: UUID
    request_type: Literal["erasure", "consent_withdrawal", "data_export"] = "erasure"
    reason: str = Field(default="", max_length=500)


class ErasureRequestResponse(BaseModel):
    id: UUID
    candidate_id: Optional[UUID] = None
    candidate_ref_hash: str
    request_type: str
    status: str
    reason: str
    requested_by: Optional[UUID] = None
    processed_by: Optional[UUID] = None
    processed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
