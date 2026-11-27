"""Pydantic v2 schemas for Phase 4 & Section Mapping: Candidate Brief, Career Timeline, and Consistency Checks."""

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
    employment_type: str = "unknown"
    raw_start: Optional[str] = None
    raw_end: Optional[str] = None
    start_ym: Optional[str] = None
    end_ym: Optional[str] = None
    start_month_index: Optional[int] = None
    end_month_index: Optional[int] = None
    duration_months: Optional[int] = None
    is_current: bool = False
    has_invalid_dates: bool = False


class TimelineEducation(BaseModel):
    index: int
    degree: str
    field_of_study: Optional[str] = None
    institution: str = ""
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    graduation_year: Optional[int] = None
    start_ym: Optional[str] = None
    end_ym: Optional[str] = None
    start_month_index: Optional[int] = None
    end_month_index: Optional[int] = None
    is_current: bool = False
    estimated: bool = False


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


class SkillEvidenceItem(BaseModel):
    skill: str
    sources: List[str] = Field(default_factory=list)  # subset of experience, projects, certification, education


class TenureStats(BaseModel):
    total_years: float
    total_months: int
    full_time_years: float = 0.0
    internship_months: int = 0
    role_count: int
    dated_role_count: int
    core_role_count: int = 0
    core_dated_role_count: int = 0
    internship_count: int = 0
    trainee_count: int = 0
    contract_count: int = 0
    average_tenure_months: float
    jobs_last_5_years: int
    short_stints_count: int


class CandidateTimelineResponse(BaseModel):
    candidate_id: UUID
    gap_threshold_months: int
    roles: List[TimelineRole] = Field(default_factory=list)
    study_windows: List[TimelineEducation] = Field(default_factory=list)
    gaps: List[TimelineGap] = Field(default_factory=list)
    overlaps: List[TimelineOverlap] = Field(default_factory=list)
    tenure_stats: TenureStats
    consistency_checks: List[ConsistencyCheckItem] = Field(default_factory=list)
    skill_evidence: List[SkillEvidenceItem] = Field(default_factory=list)
