"""Phase 4 model: cached AI/deterministic CandidateBrief (1:1 with Candidate, ON DELETE CASCADE)."""

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CandidateBrief(Base):
    """Cached concise candidate brief (<=5-line summary, strengths, worth-verifying items)."""

    __tablename__ = "candidate_briefs"

    candidate_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    verify_items: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="deterministic")
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    candidate: Mapped["Candidate"] = relationship("Candidate")


from app.models.candidate import Candidate  # noqa: E402, F401
