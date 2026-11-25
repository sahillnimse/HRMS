"""Phase 2 models: SkillNormalization and JobMatch cache."""

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SkillNormalization(Base):
    """Canonical skill name and its aliases (e.g. JavaScript <- ['JS', 'ECMAScript'])."""

    __tablename__ = "skill_normalizations"

    canonical_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class JobMatch(Base):
    """Cached deterministic JD-to-Candidate match score, structured breakdown, and LLM explanation."""

    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", name="uq_job_matches_job_candidate"),
    )

    job_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    job: Mapped["Job"] = relationship("Job")
    candidate: Mapped["Candidate"] = relationship("Candidate")


from app.models.candidate import Candidate  # noqa: E402, F401
from app.models.pipeline import Job  # noqa: E402, F401
