"""remove legacy status

Revision ID: 0007_remove_legacy_status
Revises: 0006_remove_legacy_fields
Create Date: 2026-03-15 11:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_remove_legacy_status"
down_revision = "0006_remove_legacy_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("samples") as batch_op:
        batch_op.drop_index("ix_samples_status")
        batch_op.drop_column("status")


def downgrade() -> None:
    with op.batch_alter_table("samples") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=50), nullable=True))
        batch_op.create_index("ix_samples_status", ["status"], unique=False)
