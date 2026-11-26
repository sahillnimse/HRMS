"""Phase 4: candidate_briefs table for cached AI/deterministic candidate clarity briefs.

Revision ID: 0007_phase4_candidate_clarity
Revises: 0006_phase3_scale_and_privacy
Create Date: 2026-11-26 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase4_candidate_clarity"
down_revision: Union[str, None] = "0006_phase3_scale_and_privacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "candidate_briefs" not in existing_tables:
        op.create_table(
            "candidate_briefs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("candidates.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("verify_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False, server_default="deterministic"),
            sa.Column("source_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "generated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        op.create_index("ix_candidate_briefs_candidate_id", "candidate_briefs", ["candidate_id"])
        op.create_index("ix_candidate_briefs_source_hash", "candidate_briefs", ["source_hash"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())
    if "candidate_briefs" in existing_tables:
        op.drop_table("candidate_briefs")
