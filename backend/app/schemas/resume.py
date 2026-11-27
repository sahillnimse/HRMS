"""
Pydantic v2 schemas for AI structured resume output.

These schemas define the strict JSON contract the AI parser must return for
every resume, with defensive normalization for common LLM formatting quirks
(empty strings, schemeless URLs, string numbers, etc.).
"""

import re
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field, EmailStr, HttpUrl, TypeAdapter, field_validator, model_validator

from app.services.section_mapping import (
    MAX_PROJECT_DESC_CHARS,
    MAX_PROJECT_TECHS,
    MAX_PROJECTS,
    infer_employment_type,
    normalize_employment_type_value,
    parse_education_dates,
)

_email_adapter = TypeAdapter(EmailStr)
_url_adapter = TypeAdapter(HttpUrl)

_EMPTY_SENTINELS = {"", "none", "null", "n/a", "na", "nil", "-", "—", "not provided", "unknown"}


def _clean_optional_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s.lower() in _EMPTY_SENTINELS:
            return None
        return s
    return str(v).strip() or None


def _clean_optional_url(v: Any) -> Optional[str]:
    s = _clean_optional_str(v)
    if not s:
        return None
    if not re.match(r"^https?://", s, flags=re.IGNORECASE):
        s = f"https://{s}"
    try:
        return str(_url_adapter.validate_python(s))
    except Exception:
        return None


def _clean_optional_email(v: Any) -> Optional[str]:
    s = _clean_optional_str(v)
    if not s:
        return None
    try:
        return str(_email_adapter.validate_python(s))
    except Exception:
        return None


def _clean_str_list(v: Any) -> List[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    if isinstance(v, list):
        return [str(item).strip() for item in v if item is not None and str(item).strip()]
    return []


class ContactDetails(BaseModel):
    """Contact information extracted from a resume."""

    full_name: str = Field(..., description="Candidate's full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    city: Optional[str] = Field(None, description="City / location")
    linkedin_url: Optional[HttpUrl] = Field(None, description="LinkedIn profile URL")
    github_url: Optional[HttpUrl] = Field(None, description="GitHub profile URL")
    portfolio_url: Optional[HttpUrl] = Field(None, description="Portfolio / personal website URL")

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_name(cls, v: Any) -> str:
        return _clean_optional_str(v) or "Unnamed Candidate"

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Any) -> Optional[str]:
        return _clean_optional_email(v)

    @field_validator("phone", "city", mode="before")
    @classmethod
    def normalize_optional_text(cls, v: Any) -> Optional[str]:
        return _clean_optional_str(v)

    @field_validator("linkedin_url", "github_url", "portfolio_url", mode="before")
    @classmethod
    def normalize_urls(cls, v: Any) -> Optional[str]:
        return _clean_optional_url(v)


class ProfileOverview(BaseModel):
    """High-level profile summary and experience metrics."""

    summary: str = Field(
        ...,
        description="2-3 sentence simplified summary of the candidate",
    )
    years_experience: float = Field(
        default=0.0,
        ge=0,
        description="Total years of professional experience (calculated)",
    )
    primary_domain: str = Field(
        ...,
        description="Kind of work / primary domain, e.g. Software Engineering, Digital Marketing, Operations",
    )

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, v: Any) -> str:
        return _clean_optional_str(v) or "Candidate profile parsed from resume."

    @field_validator("primary_domain", mode="before")
    @classmethod
    def normalize_domain(cls, v: Any) -> str:
        return _clean_optional_str(v) or "General"

    @field_validator("years_experience", mode="before")
    @classmethod
    def normalize_years(cls, v: Any) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            return max(0.0, float(v))
        match = re.search(r"\d+(\.\d+)?", str(v))
        return max(0.0, float(match.group(0))) if match else 0.0


EmploymentType = Literal[
    "full_time",
    "internship",
    "trainee",
    "contract",
    "freelance",
    "part_time",
    "unknown",
]


class WorkExperienceItem(BaseModel):
    """A single work experience entry."""

    company: str = Field(default="", description="Company name")
    job_title: str = Field(default="", description="Job title")
    employment_type: EmploymentType = Field(
        default="unknown",
        description="Role type: full_time, internship, trainee, contract, freelance, part_time, or unknown",
    )
    start_date: Optional[str] = Field(None, description="Start date (e.g. 'Jan 2020')")
    end_date: Optional[str] = Field(None, description="End date, or 'Present'")
    bullets: List[str] = Field(
        default_factory=list,
        description="2-4 concise bullet points summarizing what they actually did",
    )

    @field_validator("company", "job_title", mode="before")
    @classmethod
    def normalize_role_strings(cls, v: Any) -> str:
        return _clean_optional_str(v) or ""

    @field_validator("employment_type", mode="before")
    @classmethod
    def normalize_emp_type(cls, v: Any) -> str:
        return normalize_employment_type_value(v)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        return _clean_optional_str(v)

    @field_validator("bullets", mode="before")
    @classmethod
    def normalize_bullets(cls, v: Any) -> List[str]:
        return _clean_str_list(v)

    @model_validator(mode="after")
    def infer_missing_employment_type(self) -> "WorkExperienceItem":
        self.employment_type = infer_employment_type(
            self.job_title, self.company, self.employment_type
        )  # type: ignore[assignment]
        return self


class EducationItem(BaseModel):
    """A single education entry."""

    degree: str = Field(default="", description="Degree earned (e.g. B.E., B.Tech, M.S.)")
    field_of_study: Optional[str] = Field(
        None, description="Major / field of study (e.g. Computer Science)"
    )
    institution: str = Field(default="", description="Institution name")
    start_year: Optional[int] = Field(None, description="Program start year (e.g. 2020)")
    end_year: Optional[int] = Field(None, description="Program end / expected graduation year (e.g. 2024)")
    graduation_year: Optional[int] = Field(
        None, description="Graduation year (kept synced with end_year for backward compatibility)"
    )
    is_current: bool = Field(
        default=False, description="True if currently pursuing / expected graduation"
    )

    @model_validator(mode="before")
    @classmethod
    def parse_flexible_edu_dates(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        s_yr, e_yr, g_yr, is_curr = parse_education_dates(
            start_year=out.get("start_year"),
            end_year=out.get("end_year"),
            graduation_year=out.get("graduation_year"),
            date_range=out.get("date_range") if isinstance(out.get("date_range"), str) else None,
            is_current=bool(out.get("is_current")) if out.get("is_current") is not None else None,
        )
        out["start_year"] = s_yr
        out["end_year"] = e_yr
        out["graduation_year"] = g_yr
        out["is_current"] = is_curr
        out.pop("date_range", None)
        return out

    @field_validator("degree", "institution", mode="before")
    @classmethod
    def normalize_edu_strings(cls, v: Any) -> str:
        return _clean_optional_str(v) or ""

    @field_validator("field_of_study", mode="before")
    @classmethod
    def normalize_field_of_study(cls, v: Any) -> Optional[str]:
        return _clean_optional_str(v)


class ProjectItem(BaseModel):
    """A candidate project entry extracted from the resume (capped in size)."""

    name: str = Field(default="", description="Project title")
    description: str = Field(default="", description="Concise summary of what was built")
    technologies: List[str] = Field(
        default_factory=list, description="Technologies, frameworks, and tools used"
    )
    start_date: Optional[str] = Field(None, description="Optional project start date")
    end_date: Optional[str] = Field(None, description="Optional project end date")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_proj_name(cls, v: Any) -> str:
        return (_clean_optional_str(v) or "")[:120]

    @field_validator("description", mode="before")
    @classmethod
    def normalize_proj_desc(cls, v: Any) -> str:
        return (_clean_optional_str(v) or "")[:MAX_PROJECT_DESC_CHARS]

    @field_validator("technologies", mode="before")
    @classmethod
    def normalize_proj_techs(cls, v: Any) -> List[str]:
        return _clean_str_list(v)[:MAX_PROJECT_TECHS]

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_proj_dates(cls, v: Any) -> Optional[str]:
        return _clean_optional_str(v)


class Skills(BaseModel):
    """Categorized skills."""

    technical_skills: List[str] = Field(
        default_factory=list,
        description="Technical skills (programming languages, frameworks, etc.)",
    )
    tools: List[str] = Field(
        default_factory=list,
        description="Tools and platforms (Jira, AWS, Figma, etc.)",
    )
    soft_skills: List[str] = Field(
        default_factory=list,
        description="Soft skills (communication, leadership, etc.)",
    )

    @field_validator("technical_skills", "tools", "soft_skills", mode="before")
    @classmethod
    def normalize_skill_lists(cls, v: Any) -> List[str]:
        return _clean_str_list(v)


class AdditionalInfo(BaseModel):
    """Additional miscellaneous, compensation, and mobility information (extract only if explicitly present)."""

    hobbies_interests: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list, description="Languages spoken")
    certifications: List[str] = Field(default_factory=list)
    notice_period_days: Optional[int] = Field(
        None,
        ge=0,
        description="Notice period in days ONLY if explicitly mentioned in the resume, else null",
    )
    current_ctc: Optional[float] = Field(
        None,
        ge=0,
        description="Current annual CTC numeric value ONLY if explicitly mentioned, else null",
    )
    expected_ctc: Optional[float] = Field(
        None,
        ge=0,
        description="Expected annual CTC numeric value ONLY if explicitly mentioned, else null",
    )
    ctc_currency: Optional[str] = Field(
        None,
        description="3-letter currency code (e.g. INR, USD, EUR) ONLY if CTC is mentioned, else null",
    )
    preferred_locations: List[str] = Field(
        default_factory=list,
        description="Preferred work locations ONLY if explicitly stated",
    )
    open_to_relocate: Optional[bool] = Field(
        None,
        description="Whether candidate explicitly stated openness to relocate, else null",
    )

    @field_validator("hobbies_interests", "languages", "certifications", "preferred_locations", mode="before")
    @classmethod
    def normalize_additional_lists(cls, v: Any) -> List[str]:
        return _clean_str_list(v)

    @field_validator("notice_period_days", mode="before")
    @classmethod
    def normalize_notice_days(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return max(0, v)
        match = re.search(r"\d+", str(v))
        return int(match.group(0)) if match else None

    @field_validator("current_ctc", "expected_ctc", mode="before")
    @classmethod
    def normalize_ctc(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return max(0.0, float(v))
        cleaned = str(v).replace(",", "")
        match = re.search(r"\d+(\.\d+)?", cleaned)
        return max(0.0, float(match.group(0))) if match else None

    @field_validator("ctc_currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> Optional[str]:
        s = _clean_optional_str(v)
        return s.upper()[:10] if s else None

    @field_validator("open_to_relocate", mode="before")
    @classmethod
    def normalize_relocate(cls, v: Any) -> Optional[bool]:
        if v is None or v == "":
            return None
        if isinstance(v, bool):
            return v
        low = str(v).strip().lower()
        if low in {"true", "yes", "1"}:
            return True
        if low in {"false", "no", "0"}:
            return False
        return None


class ParsedResume(BaseModel):
    """Complete structured resume parsed by AI."""

    contact: ContactDetails
    profile: ProfileOverview
    work_experience: List[WorkExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    additional_info: AdditionalInfo = Field(default_factory=AdditionalInfo)

    @field_validator("work_experience", "education", mode="before")
    @classmethod
    def normalize_item_lists(cls, v: Any) -> list:
        return v if isinstance(v, list) else []

    @field_validator("projects", mode="before")
    @classmethod
    def normalize_projects_field(cls, v: Any) -> list:
        return v[:MAX_PROJECTS] if isinstance(v, list) else []

    @field_validator("skills", mode="before")
    @classmethod
    def normalize_skills_obj(cls, v: Any) -> Any:
        return v if isinstance(v, (dict, Skills)) else {}

    @field_validator("additional_info", mode="before")
    @classmethod
    def normalize_additional_obj(cls, v: Any) -> Any:
        return v if isinstance(v, (dict, AdditionalInfo)) else {}

    def to_flat_dict(self) -> dict:
        """Convert to a flat dict suitable for storing in Candidate columns."""
        return {
            "full_name": self.contact.full_name,
            "email": str(self.contact.email) if self.contact.email else None,
            "phone": self.contact.phone,
            "city": self.contact.city,
            "linkedin_url": str(self.contact.linkedin_url) if self.contact.linkedin_url else None,
            "github_url": str(self.contact.github_url) if self.contact.github_url else None,
            "portfolio_url": str(self.contact.portfolio_url) if self.contact.portfolio_url else None,
            "profile_summary": self.profile.summary,
            "years_experience": self.profile.years_experience,
            "primary_domain": self.profile.primary_domain,
            "work_experience": [we.model_dump() for we in self.work_experience],
            "education": [edu.model_dump() for edu in self.education],
            "projects": [proj.model_dump() for proj in self.projects[:MAX_PROJECTS]],
            "technical_skills": self.skills.technical_skills,
            "tools": self.skills.tools,
            "soft_skills": self.skills.soft_skills,
            "hobbies_interests": self.additional_info.hobbies_interests,
            "languages": self.additional_info.languages,
            "certifications": self.additional_info.certifications,
            "notice_period_days": self.additional_info.notice_period_days,
            "current_ctc": self.additional_info.current_ctc,
            "expected_ctc": self.additional_info.expected_ctc,
            "ctc_currency": self.additional_info.ctc_currency,
            "preferred_locations": self.additional_info.preferred_locations,
            "open_to_relocate": self.additional_info.open_to_relocate,
        }
