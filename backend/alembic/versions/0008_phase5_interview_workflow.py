"""Phase 5: interviews, interview_participants, scorecard_templates, scorecards, email_templates, email_log, offers.

Revision ID: 0008_phase5_interview_workflow
Revises: 0007_phase4_candidate_clarity
Create Date: 2026-11-26 16:25:00
"""

import json
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase5_interview_workflow"
down_revision: Union[str, None] = "0007_phase4_candidate_clarity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_SCORECARD_COMPETENCIES = [
    {
        "name": "Role & Technical Depth",
        "description": "Hands-on mastery of core skills required for the role.",
        "weight": 0.35,
    },
    {
        "name": "Problem Solving & Execution",
        "description": "Structured thinking, debugging, and pragmatic trade-offs.",
        "weight": 0.30,
    },
    {
        "name": "Communication & Collaboration",
        "description": "Clarity, listening, and ability to work across teams.",
        "weight": 0.20,
    },
    {
        "name": "Ownership & Growth",
        "description": "Accountability for outcomes and eagerness to learn.",
        "weight": 0.15,
    },
]

_DEFAULT_EMAIL_TEMPLATES = [
    (
        "interview_invite",
        "Interview Invitation: {{job_title}} ({{round_name}})",
        "Hi {{candidate_name}},\n\nWe would like to invite you for the {{round_name}} interview for the {{job_title}} role.\n\nDate & Time: {{interview_time}}\nMode / Link: {{interview_link}}\n\nPlease reply if you need to reschedule.\n\nBest regards,\nHiring Team",
        "interview",
        False,
    ),
    (
        "offer_letter",
        "Offer Details: {{job_title}}",
        "Hi {{candidate_name}},\n\nWe are excited to extend an offer for the {{job_title}} position. Our hiring team will share the formal offer documentation shortly.\n\nBest regards,\nHiring Team",
        "offer",
        False,
    ),
    (
        "rejection_notice",
        "Update on your application for {{job_title}}",
        "Hi {{candidate_name}},\n\nThank you for taking the time to speak with us regarding the {{job_title}} role. After careful review, we will not be moving forward at this time. We appreciate your interest and wish you every success.\n\nBest regards,\nHiring Team",
        None,
        False,
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())

    if "interviews" not in existing:
        op.create_table(
            "interviews",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "application_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("applications.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("round_name", sa.String(length=120), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="45"),
            sa.Column("mode", sa.String(length=20), nullable=False, server_default="video"),
            sa.Column("location_or_link", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="scheduled"),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_interviews_application_id", "interviews", ["application_id"])
        op.create_index("ix_interviews_scheduled_at", "interviews", ["scheduled_at"])
        op.create_index("ix_interviews_status", "interviews", ["status"])

    if "interview_participants" not in existing:
        op.create_table(
            "interview_participants",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "interview_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("interviews.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("interview_id", "user_id", name="uq_interview_participants_interview_user"),
        )
        op.create_index("ix_interview_participants_interview_id", "interview_participants", ["interview_id"])
        op.create_index("ix_interview_participants_user_id", "interview_participants", ["user_id"])

    if "scorecard_templates" not in existing:
        op.create_table(
            "scorecard_templates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False, unique=True),
            sa.Column("competencies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("scale", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_scorecard_templates_name", "scorecard_templates", ["name"])
        conn.execute(
            sa.text(
                "INSERT INTO scorecard_templates (id, name, competencies, scale) "
                "VALUES (:id, :name, CAST(:comp AS jsonb), 5) ON CONFLICT (name) DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "name": "General Hiring Scorecard",
                "comp": json.dumps(_DEFAULT_SCORECARD_COMPETENCIES),
            },
        )

    if "scorecards" not in existing:
        op.create_table(
            "scorecards",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "interview_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("interviews.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "interviewer_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "template_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("scorecard_templates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("ratings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("recommendation", sa.String(length=20), nullable=False),
            sa.Column("comments", sa.Text(), nullable=False, server_default=""),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("interview_id", "interviewer_id", name="uq_scorecards_interview_interviewer"),
        )
        op.create_index("ix_scorecards_interview_id", "scorecards", ["interview_id"])
        op.create_index("ix_scorecards_interviewer_id", "scorecards", ["interviewer_id"])

    if "email_templates" not in existing:
        op.create_table(
            "email_templates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("key", sa.String(length=80), nullable=False, unique=True),
            sa.Column("subject", sa.String(length=255), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("stage_trigger", sa.String(length=32), nullable=True),
            sa.Column("auto_send", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_email_templates_key", "email_templates", ["key"])
        op.create_index("ix_email_templates_stage_trigger", "email_templates", ["stage_trigger"])
        for key, subject, body, stage_trigger, auto_send in _DEFAULT_EMAIL_TEMPLATES:
            conn.execute(
                sa.text(
                    "INSERT INTO email_templates (id, key, subject, body, stage_trigger, auto_send) "
                    "VALUES (:id, :key, :subject, :body, :stage_trigger, :auto_send) "
                    "ON CONFLICT (key) DO NOTHING"
                ),
                {
                    "id": uuid.uuid4(),
                    "key": key,
                    "subject": subject,
                    "body": body,
                    "stage_trigger": stage_trigger,
                    "auto_send": auto_send,
                },
            )

    if "email_log" not in existing:
        op.create_table(
            "email_log",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "candidate_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("candidates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "application_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("applications.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("template_key", sa.String(length=80), nullable=True),
            sa.Column("to", sa.String(length=255), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_email_log_candidate_id", "email_log", ["candidate_id"])
        op.create_index("ix_email_log_application_id", "email_log", ["application_id"])
        op.create_index("ix_email_log_status", "email_log", ["status"])

    if "offers" not in existing:
        op.create_table(
            "offers",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "application_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("applications.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("offered_ctc", sa.Numeric(14, 2), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("expected_joining_date", sa.Date(), nullable=True),
            sa.Column("decline_reason", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_offers_application_id", "offers", ["application_id"])
        op.create_index("ix_offers_status", "offers", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())
    for tbl in (
        "offers",
        "email_log",
        "email_templates",
        "scorecards",
        "scorecard_templates",
        "interview_participants",
        "interviews",
    ):
        if tbl in existing:
            op.drop_table(tbl)
