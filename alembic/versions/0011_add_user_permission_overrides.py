"""add user permission overrides

Revision ID: 0011_add_user_permission_overrides
Revises: 0010_rebuild_samples_without_unique_sample_id
Create Date: 2026-03-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_add_user_permission_overrides"
down_revision = "0010_rebuild_samples_without_unique_sample_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("permissions_allow_json", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("permissions_deny_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "permissions_deny_json")
    op.drop_column("users", "permissions_allow_json")
