"""Phase 2 search & matching: GIN/trgm/tsvector indexes, skill_normalizations, job_matches, and conditional pgvector.

Revision ID: 0005_phase2_search_and_matching
Revises: 0004_phase1_hiring_pipeline
Create Date: 2026-11-25
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase2_search_and_matching"
down_revision: Union[str, None] = "0004_phase1_hiring_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SKILL_NORMALIZATIONS: list[tuple[str, list[str]]] = [
    ("JavaScript", ["JS", "ECMAScript", "Vanilla JS", "ES6"]),
    ("TypeScript", ["TS"]),
    ("React", ["ReactJS", "React.js"]),
    ("Node.js", ["Node", "NodeJS", "Node JS"]),
    ("Next.js", ["NextJS", "Next"]),
    ("PostgreSQL", ["Postgres", "PG", "PSQL"]),
    ("Python", ["Py", "Python3", "Python 3"]),
    ("FastAPI", ["Fast API"]),
    ("Kubernetes", ["K8s", "Kube"]),
    ("Docker", ["Docker Engine", "Docker Compose"]),
    ("AWS", ["Amazon Web Services"]),
    ("GCP", ["Google Cloud", "Google Cloud Platform"]),
    ("Azure", ["Microsoft Azure"]),
    ("Machine Learning", ["ML"]),
    ("Deep Learning", ["DL"]),
    ("PyTorch", ["Torch"]),
    ("Tailwind CSS", ["Tailwind", "TailwindCSS"]),
    ("MongoDB", ["Mongo"]),
    ("C++", ["CPP"]),
    ("C#", ["CSharp", "C Sharp"]),
    ("SQL", ["Structured Query Language"]),
    ("GraphQL", ["GQL"]),
    ("CI/CD", ["CICD", "GitHub Actions"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    cand_cols = {c["name"] for c in inspector.get_columns("candidates")}
    cand_indexes = {idx["name"] for idx in inspector.get_indexes("candidates")}

    # Ensure pg_trgm is available
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 1. Search vector + portable JSON embedding columns on candidates
    if "search_vector" not in cand_cols:
        op.add_column("candidates", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    if "embedding_json" not in cand_cols:
        op.add_column(
            "candidates",
            sa.Column("embedding_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )

    # Conditionally enable pgvector + native vector(768) column + HNSW index if extension is installed
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
                CREATE EXTENSION IF NOT EXISTS vector;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'candidates' AND column_name = 'embedding'
                ) THEN
                    ALTER TABLE candidates ADD COLUMN embedding vector(768);
                END IF;
                CREATE INDEX IF NOT EXISTS ix_candidates_embedding_hnsw
                    ON candidates USING hnsw (embedding vector_cosine_ops);
            END IF;
        END $$;
        """
    )

    # 2. GIN indexes on JSONB skills/tools, pg_trgm on email/domain, and GIN on search_vector
    if "ix_candidates_technical_skills_gin" not in cand_indexes:
        op.create_index(
            "ix_candidates_technical_skills_gin",
            "candidates",
            ["technical_skills"],
            postgresql_using="gin",
        )
    if "ix_candidates_tools_gin" not in cand_indexes:
        op.create_index(
            "ix_candidates_tools_gin",
            "candidates",
            ["tools"],
            postgresql_using="gin",
        )
    if "ix_candidates_email_trgm" not in cand_indexes:
        op.create_index(
            "ix_candidates_email_trgm",
            "candidates",
            ["email"],
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
        )
    if "ix_candidates_primary_domain_trgm" not in cand_indexes:
        op.create_index(
            "ix_candidates_primary_domain_trgm",
            "candidates",
            ["primary_domain"],
            postgresql_using="gin",
            postgresql_ops={"primary_domain": "gin_trgm_ops"},
        )
    if "ix_candidates_search_vector_gin" not in cand_indexes:
        op.create_index(
            "ix_candidates_search_vector_gin",
            "candidates",
            ["search_vector"],
            postgresql_using="gin",
        )

    # Backfill search_vector for existing candidates
    op.execute(
        """
        UPDATE candidates
        SET search_vector =
            setweight(to_tsvector('english', COALESCE(full_name, '') || ' ' || COALESCE(primary_domain, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE((
                SELECT string_agg(elem->>'job_title', ' ')
                FROM jsonb_array_elements(COALESCE(work_experience, '[]'::jsonb)) AS elem
            ), '')), 'A') ||
            setweight(to_tsvector('english', COALESCE((
                SELECT string_agg(val, ' ')
                FROM jsonb_array_elements_text(COALESCE(technical_skills, '[]'::jsonb) || COALESCE(tools, '[]'::jsonb)) AS val
            ), '')), 'B') ||
            setweight(to_tsvector('english', COALESCE(profile_summary, '')), 'C')
        """
    )

    # 3. skill_normalizations table + default seed
    if "skill_normalizations" not in existing_tables:
        op.create_table(
            "skill_normalizations",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("canonical_name", sa.String(length=120), nullable=False),
            sa.Column(
                "aliases",
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
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("canonical_name"),
        )
        op.create_index(
            "ix_skill_normalizations_canonical_name",
            "skill_normalizations",
            ["canonical_name"],
            unique=True,
        )

    for canonical, aliases in DEFAULT_SKILL_NORMALIZATIONS:
        op.execute(
            sa.text(
                "INSERT INTO skill_normalizations (canonical_name, aliases) "
                "VALUES (:canonical, CAST(:aliases AS jsonb)) "
                "ON CONFLICT (canonical_name) DO NOTHING"
            ).bindparams(canonical=canonical, aliases=json.dumps(aliases))
        )

    # 4. job_matches cache table
    if "job_matches" not in existing_tables:
        op.create_table(
            "job_matches",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column(
                "breakdown",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("model_version", sa.String(length=120), nullable=True),
            sa.Column(
                "computed_at",
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
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_id", "candidate_id", name="uq_job_matches_job_candidate"),
        )
        op.create_index("ix_job_matches_job_id", "job_matches", ["job_id"])
        op.create_index("ix_job_matches_candidate_id", "job_matches", ["candidate_id"])
        op.create_index("ix_job_matches_score", "job_matches", ["score"])


def downgrade() -> None:
    op.drop_table("job_matches")
    op.drop_table("skill_normalizations")

    op.drop_index("ix_candidates_search_vector_gin", table_name="candidates")
    op.drop_index("ix_candidates_primary_domain_trgm", table_name="candidates")
    op.drop_index("ix_candidates_email_trgm", table_name="candidates")
    op.drop_index("ix_candidates_tools_gin", table_name="candidates")
    op.drop_index("ix_candidates_technical_skills_gin", table_name="candidates")

    op.execute("DROP INDEX IF EXISTS ix_candidates_embedding_hnsw")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS embedding")
    op.drop_column("candidates", "embedding_json")
    op.drop_column("candidates", "search_vector")
