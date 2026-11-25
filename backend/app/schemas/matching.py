"""Pydantic v2 schemas for Phase 2: skill normalization, hybrid search, JD matching, and comparison."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.candidate import CandidateListItem, CandidateResponse


class SkillNormalizationCreate(BaseModel):
    canonical_name: str = Field(..., min_length=1, max_length=120)
    aliases: List[str] = Field(default_factory=list)


class SkillNormalizationResponse(BaseModel):
    id: UUID
    canonical_name: str
    aliases: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidateSearchItem(CandidateListItem):
    tools: List[str] = Field(default_factory=list)
    relevance_score: float = 0.0
    fts_score: float = 0.0
    trgm_score: float = 0.0
    semantic_score: float = 0.0


class CandidateSearchResponse(BaseModel):
    items: List[CandidateSearchItem]
    total: int
    page: int
    page_size: int
    pages: int
    semantic_enabled: bool = False
    semantic_used: bool = False
    normalized_skills_filter: List[str] = Field(default_factory=list)


class JobMatchRequest(BaseModel):
    candidate_ids: Optional[List[UUID]] = None
    include_explanations: bool = True


class JobMatchCandidateSummary(BaseModel):
    id: UUID
    full_name: str
    email: Optional[str] = None
    city: Optional[str] = None
    primary_domain: str
    years_experience: float
    technical_skills: List[str]
    tools: List[str] = Field(default_factory=list)
    notice_period_days: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class JobMatchItem(BaseModel):
    id: UUID
    job_id: UUID
    candidate_id: UUID
    score: float
    breakdown: Dict[str, Any]
    explanation: Optional[str] = None
    model_version: Optional[str] = None
    computed_at: datetime
    in_pipeline: bool = False
    application_stage: Optional[str] = None
    candidate: Optional[JobMatchCandidateSummary] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateCompareResponse(BaseModel):
    candidates: List[CandidateResponse]
    shared_skills: List[str]
    job_matches: Dict[str, JobMatchItem] = Field(default_factory=dict)
