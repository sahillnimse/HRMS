"""Backlog features: talent_pools, talent_pool_members, erasure_requests (DPDP), inbound_email_logs.

Revision ID: 0010_backlog_pools_dpdp
Revises: 0009_section_mapping_projects
Create Date: 2026-11-28 13:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_backlog_pools_dpdp"
down_revision: Union[str, None] = "0009_section_mapping_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())

    if "talent_pools" not in existing:
        op.create_table(
            "talent_pools",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("color", sa.String(length=32), nullable=False, server_default="teal"),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_talent_pools_name", "talent_pools", ["name"])

    if "talent_pool_members" not in existing:
        op.create_table(
            "talent_pool_members",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "pool_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("talent_pools.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("candidates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "added_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("pool_id", "candidate_id", name="uq_talent_pool_members_pool_cand"),
        )
        op.create_index("ix_talent_pool_members_pool_id", "talent_pool_members", ["pool_id"])
        op.create_index("ix_talent_pool_members_candidate_id", "talent_pool_members", ["candidate_id"])

    if "erasure_requests" not in existing:
        op.create_table(
            "erasure_requests",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("candidates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("candidate_ref_hash", sa.String(length=64), nullable=False),
            sa.Column("request_type", sa.String(length=32), nullable=False, server_default="erasure"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "requested_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "processed_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_erasure_requests_candidate_id", "erasure_requests", ["candidate_id"])
        op.create_index("ix_erasure_requests_status", "erasure_requests", ["status"])

    if "inbound_email_logs" not in existing:
        op.create_table(
            "inbound_email_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("message_id", sa.String(length=255), nullable=False, unique=True),
            sa.Column("from_domain", sa.String(length=120), nullable=False, server_default="unknown"),
            sa.Column("subject", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("attachment_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("parse_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="processed"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_inbound_email_logs_message_id", "inbound_email_logs", ["message_id"])
        op.create_index("ix_inbound_email_logs_status", "inbound_email_logs", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())
    for tbl in (
        "inbound_email_logs",
        "erasure_requests",
        "talent_pool_members",
        "talent_pools",
    ):
        if tbl in existing:
            op.drop_table(tbl)
