"""Hiring pipeline models: Job, Application, ApplicationEvent, CandidateNote, AuditLog."""

from datetime import datetime
import enum
from uuid import UUID as PyUUID

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    closed = "closed"


class ApplicationStage(str, enum.Enum):
    applied = "applied"
    screened = "screened"
    interview = "interview"
    offer = "offer"
    hired = "hired"
    rejected = "rejected"


class Job(Base):
    """Job requisition with skill requirements, experience range, and status."""

    __tablename__ = "jobs"

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    required_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    nice_to_have_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    min_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status", create_constraint=False),
        nullable=False,
        default=JobStatus.draft,
        index=True,
    )
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    applications: Mapped[list["Application"]] = relationship(
        "Application",
        back_populates="job",
        cascade="all, delete-orphan",
    )


class Application(Base):
    """Links a Candidate to a Job and tracks their current pipeline stage."""

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_applications_candidate_job"),
    )

    candidate_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[ApplicationStage] = mapped_column(
        SAEnum(ApplicationStage, name="application_stage", create_constraint=False),
        nullable=False,
        default=ApplicationStage.applied,
        index=True,
    )
    stage_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    job: Mapped["Job"] = relationship("Job", back_populates="applications")
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="applications")
    events: Mapped[list["ApplicationEvent"]] = relationship(
        "ApplicationEvent",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.created_at.desc()",
    )


class ApplicationEvent(Base):
    """Immutable stage transition history for an Application."""

    __tablename__ = "application_events"

    application_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship("Application", back_populates="events")
    actor: Mapped["User | None"] = relationship("User")


class CandidateNote(Base):
    """Recruiter/interviewer notes with tags attached to a candidate."""

    __tablename__ = "candidate_notes"

    candidate_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="notes")
    author: Mapped["User | None"] = relationship("User")


class AuditLog(Base):
    """Audit trail recording view, edit, export, delete, and stage-change actions."""

    __tablename__ = "audit_logs"

    user_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    details: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user: Mapped["User | None"] = relationship("User")


# Forward-reference imports for type-checking clarity
from app.models.candidate import Candidate  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
