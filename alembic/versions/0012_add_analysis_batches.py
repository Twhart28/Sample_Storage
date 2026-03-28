"""add analysis batch tracking

Revision ID: 0012_add_analysis_batches
Revises: 0011_add_user_permission_overrides
Create Date: 2026-03-27 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_add_analysis_batches"
down_revision = "0011_add_user_permission_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_type", sa.String(length=100), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overall_notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_batches_analysis_type", "analysis_batches", ["analysis_type"])
    op.create_index("ix_analysis_batches_performed_at", "analysis_batches", ["performed_at"])
    op.create_index("ix_analysis_batches_user_id", "analysis_batches", ["user_id"])
    op.create_index("ix_analysis_batches_created_at", "analysis_batches", ["created_at"])

    op.create_table(
        "analysis_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("sample_id", sa.Integer(), nullable=False),
        sa.Column("from_position_id", sa.Integer(), nullable=True),
        sa.Column("to_position_id", sa.Integer(), nullable=True),
        sa.Column("remaining_volume", sa.Float(), nullable=True),
        sa.Column("volume_units", sa.String(length=20), nullable=True),
        sa.Column("thaw_increment", sa.Integer(), nullable=False),
        sa.Column("returned_to_storage", sa.Boolean(), nullable=False),
        sa.Column("sample_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["analysis_batches.id"]),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"]),
        sa.ForeignKeyConstraint(["from_position_id"], ["storage_positions.id"]),
        sa.ForeignKeyConstraint(["to_position_id"], ["storage_positions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_items_batch_id", "analysis_items", ["batch_id"])
    op.create_index("ix_analysis_items_sample_id", "analysis_items", ["sample_id"])
    op.create_index("ix_analysis_items_created_at", "analysis_items", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_analysis_items_created_at", table_name="analysis_items")
    op.drop_index("ix_analysis_items_sample_id", table_name="analysis_items")
    op.drop_index("ix_analysis_items_batch_id", table_name="analysis_items")
    op.drop_table("analysis_items")

    op.drop_index("ix_analysis_batches_created_at", table_name="analysis_batches")
    op.drop_index("ix_analysis_batches_user_id", table_name="analysis_batches")
    op.drop_index("ix_analysis_batches_performed_at", table_name="analysis_batches")
    op.drop_index("ix_analysis_batches_analysis_type", table_name="analysis_batches")
    op.drop_table("analysis_batches")
