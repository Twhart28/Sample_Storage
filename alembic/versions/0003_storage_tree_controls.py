"""storage nicknames and tree controls

Revision ID: 0003_storage_tree_controls
Revises: 0002_architecture_refresh
Create Date: 2026-03-09 00:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_storage_tree_controls"
down_revision = "0002_architecture_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("storage_nodes", sa.Column("nickname", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("storage_nodes", "nickname")
