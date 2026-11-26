"""Phase 5 models: Interviews, Participants, Scorecards, Email Templates/Log, and Offers."""

from datetime import date, datetime
from decimal import Decimal
import enum
from uuid import UUID as PyUUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InterviewMode(str, enum.Enum):
    video = "video"
    phone = "phone"
    onsite = "onsite"


class InterviewStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class ScorecardRecommendation(str, enum.Enum):
    strong_no = "strong_no"
    no = "no"
    yes = "yes"
    strong_yes = "strong_yes"


class EmailStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"


class OfferStatus(str, enum.Enum):
    draft = "draft"
    extended = "extended"
    accepted = "accepted"
    declined = "declined"
    withdrawn = "withdrawn"


class Interview(Base):
    __tablename__ = "interviews"

    application_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_name: Mapped[str] = mapped_column(String(120), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default=InterviewMode.video.value)
    location_or_link: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=InterviewStatus.scheduled.value,
        index=True,
    )
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    application: Mapped["Application"] = relationship("Application")
    participants: Mapped[list["InterviewParticipant"]] = relationship(
        "InterviewParticipant",
        back_populates="interview",
        cascade="all, delete-orphan",
    )
    scorecards: Mapped[list["Scorecard"]] = relationship(
        "Scorecard",
        back_populates="interview",
        cascade="all, delete-orphan",
    )


class InterviewParticipant(Base):
    __tablename__ = "interview_participants"
    __table_args__ = (
        UniqueConstraint("interview_id", "user_id", name="uq_interview_participants_interview_user"),
    )

    interview_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    interview: Mapped["Interview"] = relationship("Interview", back_populates="participants")
    user: Mapped["User"] = relationship("User")


class ScorecardTemplate(Base):
    __tablename__ = "scorecard_templates"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    competencies: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    scale: Mapped[int] = mapped_column(Integer, nullable=False, default=5)


class Scorecard(Base):
    __tablename__ = "scorecards"
    __table_args__ = (
        UniqueConstraint("interview_id", "interviewer_id", name="uq_scorecards_interview_interviewer"),
    )

    interview_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interviewer_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scorecard_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    ratings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recommendation: Mapped[str] = mapped_column(String(20), nullable=False)
    comments: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    interview: Mapped["Interview"] = relationship("Interview", back_populates="scorecards")
    interviewer: Mapped["User"] = relationship("User")
    template: Mapped["ScorecardTemplate | None"] = relationship("ScorecardTemplate")


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    stage_trigger: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    auto_send: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class EmailLog(Base):
    __tablename__ = "email_log"

    candidate_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    template_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_email: Mapped[str] = mapped_column("to", String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EmailStatus.queued.value,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    candidate: Mapped["Candidate"] = relationship("Candidate")
    actor: Mapped["User | None"] = relationship("User")


class Offer(Base):
    __tablename__ = "offers"

    application_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offered_ctc: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OfferStatus.draft.value,
        index=True,
    )
    expected_joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    application: Mapped["Application"] = relationship("Application")


from app.models.candidate import Candidate  # noqa: E402, F401
from app.models.pipeline import Application  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
