"""Phase 1 hiring pipeline: jobs, applications, application_events, candidate_notes, audit_logs, and candidate CTC/mobility columns.

Revision ID: 0004_phase1_hiring_pipeline
Revises: 0003_auth_hardening
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase1_hiring_pipeline"
down_revision: Union[str, None] = "0003_auth_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Enums
    job_status_enum = postgresql.ENUM("draft", "open", "closed", name="job_status", create_type=True)
    job_status_enum.create(bind, checkfirst=True)

    app_stage_enum = postgresql.ENUM(
        "applied",
        "screened",
        "interview",
        "offer",
        "hired",
        "rejected",
        name="application_stage",
        create_type=True,
    )
    app_stage_enum.create(bind, checkfirst=True)

    # 1. jobs
    if "jobs" not in existing_tables:
        op.create_table(
            "jobs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("department", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("location", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "required_skills",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "nice_to_have_skills",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("min_years", sa.Float(), nullable=True),
            sa.Column("max_years", sa.Float(), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM("draft", "open", "closed", name="job_status", create_type=False),
                nullable=False,
                server_default="draft",
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_jobs_title", "jobs", ["title"])
        op.create_index("ix_jobs_department", "jobs", ["department"])
        op.create_index("ix_jobs_status", "jobs", ["status"])
        op.create_index("ix_jobs_created_by", "jobs", ["created_by"])

    # 2. applications
    if "applications" not in existing_tables:
        op.create_table(
            "applications",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "stage",
                postgresql.ENUM(
                    "applied",
                    "screened",
                    "interview",
                    "offer",
                    "hired",
                    "rejected",
                    name="application_stage",
                    create_type=False,
                ),
                nullable=False,
                server_default="applied",
            ),
            sa.Column(
                "stage_changed_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("candidate_id", "job_id", name="uq_applications_candidate_job"),
        )
        op.create_index("ix_applications_candidate_id", "applications", ["candidate_id"])
        op.create_index("ix_applications_job_id", "applications", ["job_id"])
        op.create_index("ix_applications_stage", "applications", ["stage"])

    # 3. application_events
    if "application_events" not in existing_tables:
        op.create_table(
            "application_events",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("from_stage", sa.String(length=32), nullable=True),
            sa.Column("to_stage", sa.String(length=32), nullable=False),
            sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_application_events_application_id", "application_events", ["application_id"])

    # 4. candidate_notes
    if "candidate_notes" not in existing_tables:
        op.create_table(
            "candidate_notes",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column(
                "tags",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_candidate_notes_candidate_id", "candidate_notes", ["candidate_id"])
        op.create_index("ix_candidate_notes_author_id", "candidate_notes", ["author_id"])

    # 5. audit_logs
    if "audit_logs" not in existing_tables:
        op.create_table(
            "audit_logs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("entity", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=64), nullable=False),
            sa.Column(
                "metadata",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_entity", "audit_logs", ["entity"])
        op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
        op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])

    # 6. Candidate CTC & mobility fields
    cand_cols = {c["name"] for c in inspector.get_columns("candidates")}
    if "notice_period_days" not in cand_cols:
        op.add_column("candidates", sa.Column("notice_period_days", sa.Integer(), nullable=True))
    if "current_ctc" not in cand_cols:
        op.add_column("candidates", sa.Column("current_ctc", sa.Numeric(14, 2), nullable=True))
    if "expected_ctc" not in cand_cols:
        op.add_column("candidates", sa.Column("expected_ctc", sa.Numeric(14, 2), nullable=True))
    if "ctc_currency" not in cand_cols:
        op.add_column("candidates", sa.Column("ctc_currency", sa.String(length=10), nullable=True))
    if "preferred_locations" not in cand_cols:
        op.add_column(
            "candidates",
            sa.Column(
                "preferred_locations",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
    if "open_to_relocate" not in cand_cols:
        op.add_column("candidates", sa.Column("open_to_relocate", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "open_to_relocate")
    op.drop_column("candidates", "preferred_locations")
    op.drop_column("candidates", "ctc_currency")
    op.drop_column("candidates", "expected_ctc")
    op.drop_column("candidates", "current_ctc")
    op.drop_column("candidates", "notice_period_days")

    op.drop_table("audit_logs")
    op.drop_table("candidate_notes")
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_table("jobs")

    op.execute("DROP TYPE IF EXISTS application_stage")
    op.execute("DROP TYPE IF EXISTS job_status")
