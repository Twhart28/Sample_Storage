"""storage notes

Revision ID: 0004_storage_notes
Revises: 0003_storage_tree_controls
Create Date: 2026-03-09 00:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_storage_notes"
down_revision = "0003_storage_tree_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("storage_nodes", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("storage_nodes", "notes")
