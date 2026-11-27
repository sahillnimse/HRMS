"""Stage 1 section mapping: add projects JSONB column to candidates.

Revision ID: 0009_section_mapping_projects
Revises: 0008_phase5_interview_workflow
Create Date: 2026-11-27 14:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_section_mapping_projects"
down_revision: Union[str, None] = "0008_phase5_interview_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cand_cols = {c["name"] for c in insp.get_columns("candidates")}

    if "projects" not in cand_cols:
        op.add_column(
            "candidates",
            sa.Column(
                "projects",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cand_cols = {c["name"] for c in insp.get_columns("candidates")}

    if "projects" in cand_cols:
        op.drop_column("candidates", "projects")
