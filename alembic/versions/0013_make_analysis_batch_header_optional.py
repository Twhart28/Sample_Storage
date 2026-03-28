"""make analysis batch header optional

Revision ID: 0013_make_analysis_batch_header_optional
Revises: 0012_add_analysis_batches
Create Date: 2026-03-27 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_make_analysis_batch_header_optional"
down_revision = "0012_add_analysis_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_batches") as batch_op:
        batch_op.alter_column("analysis_type", existing_type=sa.String(length=100), nullable=True)
        batch_op.alter_column("performed_at", existing_type=sa.DateTime(timezone=True), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("analysis_batches") as batch_op:
        batch_op.alter_column("performed_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("analysis_type", existing_type=sa.String(length=100), nullable=False)
