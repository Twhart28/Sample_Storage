"""add visit workflows

Revision ID: 0015_add_visit_workflows
Revises: 0014_replace_sample_state_with_study_role
Create Date: 2026-03-28 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_add_visit_workflows"
down_revision = "0014_replace_sample_state_with_study_role"
branch_labels = None
depends_on = None


visit_session_status_enum = sa.Enum("draft", "completed", "cancelled", name="visitsessionstatus")


def upgrade() -> None:
    op.create_table(
        "study_workflows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sample_template_config_json", sa.Text(), nullable=True),
        sa.Column("quick_links_json", sa.Text(), nullable=True),
        sa.Column("summary_sections_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("study_id", name="uq_study_workflows_study_id"),
    )
    op.create_index("ix_study_workflows_study_id", "study_workflows", ["study_id"])
    op.create_index("ix_study_workflows_is_active", "study_workflows", ["is_active"])

    op.create_table(
        "visit_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("study_workflows.id"), nullable=False),
        sa.Column("participant_id", sa.String(length=100), nullable=False),
        sa.Column("visit_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", visit_session_status_enum, nullable=False, server_default="draft"),
        sa.Column("session_notes", sa.Text(), nullable=True),
        sa.Column("deviation_notes", sa.Text(), nullable=True),
        sa.Column("completion_note", sa.Text(), nullable=True),
        sa.Column("generated_workbook_filename", sa.String(length=255), nullable=True),
        sa.Column("uploaded_workbook_filename", sa.String(length=255), nullable=True),
        sa.Column("uploaded_workbook_payload_json", sa.Text(), nullable=True),
        sa.Column("step_status_json", sa.Text(), nullable=True),
        sa.Column("imported_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_visit_sessions_study_id", "visit_sessions", ["study_id"])
    op.create_index("ix_visit_sessions_workflow_id", "visit_sessions", ["workflow_id"])
    op.create_index("ix_visit_sessions_participant_id", "visit_sessions", ["participant_id"])
    op.create_index("ix_visit_sessions_visit_date", "visit_sessions", ["visit_date"])
    op.create_index("ix_visit_sessions_operator_user_id", "visit_sessions", ["operator_user_id"])
    op.create_index("ix_visit_sessions_status", "visit_sessions", ["status"])
    op.create_index("ix_visit_sessions_completed_at", "visit_sessions", ["completed_at"])
    op.create_index("ix_visit_sessions_created_at", "visit_sessions", ["created_at"])
    op.create_index("ix_visit_sessions_updated_at", "visit_sessions", ["updated_at"])

    op.create_table(
        "visit_session_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("visit_session_id", sa.Integer(), sa.ForeignKey("visit_sessions.id"), nullable=False),
        sa.Column("sample_id", sa.Integer(), sa.ForeignKey("samples.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("visit_session_id", "sample_id", name="uq_visit_session_sample"),
    )
    op.create_index("ix_visit_session_samples_visit_session_id", "visit_session_samples", ["visit_session_id"])
    op.create_index("ix_visit_session_samples_sample_id", "visit_session_samples", ["sample_id"])


def downgrade() -> None:
    op.drop_index("ix_visit_session_samples_sample_id", table_name="visit_session_samples")
    op.drop_index("ix_visit_session_samples_visit_session_id", table_name="visit_session_samples")
    op.drop_table("visit_session_samples")

    op.drop_index("ix_visit_sessions_updated_at", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_created_at", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_completed_at", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_status", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_operator_user_id", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_visit_date", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_participant_id", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_workflow_id", table_name="visit_sessions")
    op.drop_index("ix_visit_sessions_study_id", table_name="visit_sessions")
    op.drop_table("visit_sessions")

    op.drop_index("ix_study_workflows_is_active", table_name="study_workflows")
    op.drop_index("ix_study_workflows_study_id", table_name="study_workflows")
    op.drop_table("study_workflows")
