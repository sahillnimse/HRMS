from datetime import datetime
from decimal import Decimal
import enum
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResumeFileStatus(str, enum.Enum):
    pending = "pending"
    attached = "attached"


class ParseJobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class ResumeFile(Base):
    """Metadata for an uploaded resume file stored on disk/object storage."""

    __tablename__ = "resume_files"

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ResumeFileStatus.pending.value,
        server_default=ResumeFileStatus.pending.value,
        index=True,
    )

    candidate: Mapped["Candidate | None"] = relationship(
        "Candidate",
        back_populates="resume_file",
        uselist=False,
    )


class Candidate(Base):
    """
    Candidate record. Commonly filtered/searchable fields are standard indexed
    columns; nested resume sections live in JSONB columns.
    """

    __tablename__ = "candidates"
    __table_args__ = (
        Index(
            "ix_candidates_full_name_trgm",
            "full_name",
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_candidates_email_trgm",
            "email",
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
        ),
        Index(
            "ix_candidates_primary_domain_trgm",
            "primary_domain",
            postgresql_using="gin",
            postgresql_ops={"primary_domain": "gin_trgm_ops"},
        ),
        Index(
            "ix_candidates_technical_skills_gin",
            "technical_skills",
            postgresql_using="gin",
        ),
        Index(
            "ix_candidates_tools_gin",
            "tools",
            postgresql_using="gin",
        ),
        Index(
            "ix_candidates_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    # --- Contact Details (indexed for search/dedup) ---
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # --- Profile Overview ---
    profile_summary: Mapped[str] = mapped_column(Text, nullable=False)
    years_experience: Mapped[float] = mapped_column(nullable=False, default=0.0, index=True)
    primary_domain: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # --- Work Experience & Education (JSONB) ---
    work_experience: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    education: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # --- Skills (JSONB arrays) ---
    technical_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    soft_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # --- Additional Info (JSONB arrays) ---
    hobbies_interests: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    certifications: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # --- Compensation & Mobility (CTC fields visible to admin/recruiter only) ---
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    expected_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    ctc_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    preferred_locations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    open_to_relocate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- Full raw parsed payload from AI ---
    raw_parsed_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- Search & semantic vector columns (Phase 2) ---
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    embedding_json: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)

    # --- Privacy, Consent & Provenance (Phase 3) ---
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="upload",
        server_default="upload",
        index=True,
    )

    # --- Duplicate flagging ---
    is_duplicate_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- File storage relationship ---
    resume_file_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_file: Mapped["ResumeFile | None"] = relationship(
        "ResumeFile",
        back_populates="candidate",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["CandidateNote"]] = relationship(
        "CandidateNote",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class ParseJob(Base):
    """Background bulk-upload resume parsing job (Phase 3)."""

    __tablename__ = "parse_jobs"

    batch_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    resume_file_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ParseJobStatus.queued.value,
        server_default=ParseJobStatus.queued.value,
        index=True,
    )
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duplicate_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
