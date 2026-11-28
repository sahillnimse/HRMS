"""Backlog ORM models: TalentPool, TalentPoolMember, ErasureRequest (DPDP), InboundEmailLog."""

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TalentPool(Base):
    """Named curated talent pool / tag group for resurfacing strong candidates."""

    __tablename__ = "talent_pools"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="teal", server_default="teal")
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    members: Mapped[list["TalentPoolMember"]] = relationship(
        "TalentPoolMember",
        back_populates="pool",
        cascade="all, delete-orphan",
    )


class TalentPoolMember(Base):
    """Association between a TalentPool and a Candidate (ON DELETE CASCADE)."""

    __tablename__ = "talent_pool_members"
    __table_args__ = (
        UniqueConstraint("pool_id", "candidate_id", name="uq_talent_pool_members_pool_cand"),
    )

    pool_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("talent_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    added_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    pool: Mapped["TalentPool"] = relationship("TalentPool", back_populates="members")
    candidate: Mapped["Candidate"] = relationship("Candidate")


class ErasureRequest(Base):
    """
    India DPDP Act consent-withdrawal / data-erasure request ledger.
    `candidate_id` uses ON DELETE SET NULL so PII-free compliance proof survives erasure.
    """

    __tablename__ = "erasure_requests"

    candidate_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_ref_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="erasure", server_default="erasure"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending", index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    requested_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    processed_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InboundEmailLog(Base):
    """Idempotency & audit log for email-to-inbox CV ingestion (stores domain only, no PII)."""

    __tablename__ = "inbound_email_logs"

    message_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    from_domain: Mapped[str] = mapped_column(
        String(120), nullable=False, default="unknown", server_default="unknown"
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    attachment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    parse_batch_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="processed", server_default="processed", index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


from app.models.candidate import Candidate  # noqa: E402, F401
