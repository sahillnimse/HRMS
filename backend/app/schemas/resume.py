"""
Pydantic v2 schemas for Google Gemini structured output.

These schemas define the strict JSON contract the AI parser must return for
every resume. They are also used to validate the Gemini response before
persisting to PostgreSQL.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr, HttpUrl


class ContactDetails(BaseModel):
    """Contact information extracted from a resume."""

    full_name: str = Field(..., description="Candidate's full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    city: Optional[str] = Field(None, description="City / location")
    linkedin_url: Optional[HttpUrl] = Field(None, description="LinkedIn profile URL")
    github_url: Optional[HttpUrl] = Field(None, description="GitHub profile URL")
    portfolio_url: Optional[HttpUrl] = Field(None, description="Portfolio / personal website URL")


class ProfileOverview(BaseModel):
    """High-level profile summary and experience metrics."""

    summary: str = Field(
        ...,
        description="2–3 sentence simplified summary of the candidate",
    )
    years_experience: float = Field(
        ...,
        ge=0,
        description="Total years of professional experience (calculated)",
    )
    primary_domain: str = Field(
        ...,
        description="Kind of work / primary domain, e.g. Software Engineering, Digital Marketing, Operations",
    )


class WorkExperienceItem(BaseModel):
    """A single work experience entry."""

    company: str = Field(..., description="Company name")
    job_title: str = Field(..., description="Job title")
    start_date: Optional[str] = Field(None, description="Start date (e.g. 'Jan 2020')")
    end_date: Optional[str] = Field(None, description="End date, or 'Present'")
    bullets: List[str] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="2–4 concise bullet points summarizing what they actually did",
    )


class EducationItem(BaseModel):
    """A single education entry."""

    degree: str = Field(..., description="Degree earned")
    institution: str = Field(..., description="Institution name")
    graduation_year: Optional[int] = Field(None, description="Graduation year")


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


class AdditionalInfo(BaseModel):
    """Additional miscellaneous information."""

    hobbies_interests: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list, description="Languages spoken")
    certifications: List[str] = Field(default_factory=list)


class ParsedResume(BaseModel):
    """Complete structured resume parsed by Gemini."""

    contact: ContactDetails
    profile: ProfileOverview
    work_experience: List[WorkExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    additional_info: AdditionalInfo = Field(default_factory=AdditionalInfo)

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
            "technical_skills": self.skills.technical_skills,
            "tools": self.skills.tools,
            "soft_skills": self.skills.soft_skills,
            "hobbies_interests": self.additional_info.hobbies_interests,
            "languages": self.additional_info.languages,
            "certifications": self.additional_info.certifications,
        }
