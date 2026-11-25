"""Phase 3: bulk parse_jobs queue table and candidate consent/source privacy columns.

Revision ID: 0006_phase3_scale_and_privacy
Revises: 0005_phase2_search_and_matching
Create Date: 2026-11-25 16:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase3_scale_and_privacy"
down_revision: Union[str, None] = "0005_phase2_search_and_matching"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 1. Privacy & provenance columns on candidates
    cand_cols = {c["name"] for c in insp.get_columns("candidates")}
    if "consent_given_at" not in cand_cols:
        op.add_column(
            "candidates",
            sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "source" not in cand_cols:
        op.add_column(
            "candidates",
            sa.Column("source", sa.String(length=80), nullable=False, server_default="upload"),
        )
    cand_indexes = {ix["name"] for ix in insp.get_indexes("candidates")}
    if "ix_candidates_source" not in cand_indexes:
        op.create_index("ix_candidates_source", "candidates", ["source"])

    # 2. Bulk upload parse_jobs queue table
    existing_tables = set(insp.get_table_names())
    if "parse_jobs" not in existing_tables:
        op.create_table(
            "parse_jobs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "resume_file_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("resume_files.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
            sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("duplicate_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("ocr_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_parse_jobs_batch_id", "parse_jobs", ["batch_id"])
        op.create_index("ix_parse_jobs_resume_file_id", "parse_jobs", ["resume_file_id"])
        op.create_index("ix_parse_jobs_status", "parse_jobs", ["status"])
        op.create_index("ix_parse_jobs_created_by", "parse_jobs", ["created_by"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "parse_jobs" in existing_tables:
        op.drop_table("parse_jobs")

    cand_indexes = {ix["name"] for ix in insp.get_indexes("candidates")}
    if "ix_candidates_source" in cand_indexes:
        op.drop_index("ix_candidates_source", table_name="candidates")

    cand_cols = {c["name"] for c in insp.get_columns("candidates")}
    if "source" in cand_cols:
        op.drop_column("candidates", "source")
    if "consent_given_at" in cand_cols:
        op.drop_column("candidates", "consent_given_at")
