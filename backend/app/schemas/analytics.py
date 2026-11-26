"""Pydantic response schemas for Phase 6 Hiring Analytics (derived from ApplicationEvent)."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FunnelStageMetric(BaseModel):
    stage: str
    reached_count: int
    current_count: int
    conversion_from_previous_pct: Optional[float] = None
    conversion_from_applied_pct: Optional[float] = None


class FunnelAnalyticsResponse(BaseModel):
    total_applications: int
    active_applications: int
    hired_count: int
    rejected_count: int
    overall_hire_rate_pct: float
    stages: List[FunnelStageMetric] = Field(default_factory=list)


class TimeInStageMetric(BaseModel):
    stage: str
    avg_days: Optional[float] = None
    median_days: Optional[float] = None
    min_days: Optional[float] = None
    max_days: Optional[float] = None
    sample_count: int = 0


class TimeInStageResponse(BaseModel):
    stages: List[TimeInStageMetric] = Field(default_factory=list)


class TimeToHireResponse(BaseModel):
    hired_count: int
    avg_days: Optional[float] = None
    median_days: Optional[float] = None
    min_days: Optional[float] = None
    max_days: Optional[float] = None


class SourceMetric(BaseModel):
    source: str
    candidates_count: int
    applications_count: int
    screened_count: int
    interview_count: int
    hired_count: int
    hire_rate_pct: float


class SourcesAnalyticsResponse(BaseModel):
    total_candidates: int
    sources: List[SourceMetric] = Field(default_factory=list)


class StuckCandidateItem(BaseModel):
    application_id: UUID
    candidate_id: UUID
    candidate_name: str
    job_id: UUID
    job_title: str
    stage: str
    days_in_stage: float
    threshold_days: int
    stage_changed_at: datetime


class StuckCandidatesResponse(BaseModel):
    thresholds: Dict[str, int]
    total_stuck: int
    items: List[StuckCandidateItem] = Field(default_factory=list)
