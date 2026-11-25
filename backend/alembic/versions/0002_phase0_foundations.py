"""Phase 0 foundations: users table, resume_files.status, phone_normalized, pg_trgm fuzzy name index.

Revision ID: 0002_phase0_foundations
Revises: 0001_baseline
Create Date: 2026-11-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase0_foundations"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Enable pg_trgm for fuzzy name matching
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Users table with role enum
    user_role_enum = postgresql.ENUM(
        "admin", "recruiter", "viewer", name="user_role", create_type=True
    )
    user_role_enum.create(bind, checkfirst=True)

    existing_tables = set(inspector.get_table_names())
    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "role",
                postgresql.ENUM("admin", "recruiter", "viewer", name="user_role", create_type=False),
                nullable=False,
                server_default="recruiter",
            ),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    # resume_files.status (pending | attached) for orphan cleanup
    rf_cols = {c["name"] for c in inspector.get_columns("resume_files")}
    if "status" not in rf_cols:
        op.add_column(
            "resume_files",
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        )
        op.create_index("ix_resume_files_status", "resume_files", ["status"])

    # Backfill existing attached resume files
    op.execute(
        "UPDATE resume_files SET status = 'attached' "
        "WHERE id IN (SELECT resume_file_id FROM candidates WHERE resume_file_id IS NOT NULL)"
    )

    # candidates.phone_normalized + email lowercase normalization + pg_trgm index on full_name
    cand_cols = {c["name"] for c in inspector.get_columns("candidates")}
    if "phone_normalized" not in cand_cols:
        op.add_column(
            "candidates",
            sa.Column("phone_normalized", sa.String(length=32), nullable=True),
        )
        op.create_index("ix_candidates_phone_normalized", "candidates", ["phone_normalized"])

    op.execute("UPDATE candidates SET email = LOWER(TRIM(email)) WHERE email IS NOT NULL")
    op.execute(
        "UPDATE candidates "
        "SET phone_normalized = LTRIM("
        "  CASE WHEN LENGTH(REGEXP_REPLACE(phone, '\\D', '', 'g')) = 12 "
        "        AND LEFT(REGEXP_REPLACE(phone, '\\D', '', 'g'), 2) = '91' "
        "       THEN SUBSTRING(REGEXP_REPLACE(phone, '\\D', '', 'g') FROM 3) "
        "       ELSE REGEXP_REPLACE(phone, '\\D', '', 'g') END, '0') "
        "WHERE phone IS NOT NULL AND LENGTH(REGEXP_REPLACE(phone, '\\D', '', 'g')) >= 7"
    )

    cand_indexes = {idx["name"] for idx in inspector.get_indexes("candidates")}
    if "ix_candidates_full_name_trgm" not in cand_indexes:
        op.create_index(
            "ix_candidates_full_name_trgm",
            "candidates",
            ["full_name"],
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        )


def downgrade() -> None:
    op.drop_index("ix_candidates_full_name_trgm", table_name="candidates")
    op.drop_index("ix_candidates_phone_normalized", table_name="candidates")
    op.drop_column("candidates", "phone_normalized")

    op.drop_index("ix_resume_files_status", table_name="resume_files")
    op.drop_column("resume_files", "status")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")
