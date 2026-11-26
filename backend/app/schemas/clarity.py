"""Pydantic v2 schemas for Phase 4: Candidate Brief, Career Timeline, and Consistency Checks."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConsistencyCheckItem(BaseModel):
    """Informational-only verification item (never auto-rejects or alters match scores)."""

    code: str
    severity: Literal["info", "check"] = "info"
    message: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class CandidateBriefResponse(BaseModel):
    candidate_id: UUID
    summary: str
    strengths: List[str] = Field(default_factory=list)
    verify_items: List[ConsistencyCheckItem] = Field(default_factory=list)
    model: str
    source_hash: str
    generated_at: datetime
    cached: bool = True

    model_config = ConfigDict(from_attributes=True)


class TimelineRole(BaseModel):
    index: int
    company: str
    job_title: str
    raw_start: Optional[str] = None
    raw_end: Optional[str] = None
    start_ym: Optional[str] = None
    end_ym: Optional[str] = None
    start_month_index: Optional[int] = None
    end_month_index: Optional[int] = None
    duration_months: Optional[int] = None
    is_current: bool = False
    has_invalid_dates: bool = False


class TimelineGap(BaseModel):
    from_ym: str
    to_ym: str
    duration_months: int
    between_roles: List[str] = Field(default_factory=list)


class TimelineOverlap(BaseModel):
    from_ym: str
    to_ym: str
    overlap_months: int
    roles: List[str] = Field(default_factory=list)


class TenureStats(BaseModel):
    total_years: float
    total_months: int
    role_count: int
    dated_role_count: int
    average_tenure_months: float
    jobs_last_5_years: int
    short_stints_count: int


class CandidateTimelineResponse(BaseModel):
    candidate_id: UUID
    gap_threshold_months: int
    roles: List[TimelineRole] = Field(default_factory=list)
    gaps: List[TimelineGap] = Field(default_factory=list)
    overlaps: List[TimelineOverlap] = Field(default_factory=list)
    tenure_stats: TenureStats
    consistency_checks: List[ConsistencyCheckItem] = Field(default_factory=list)
