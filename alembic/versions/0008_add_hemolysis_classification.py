"""add hemolysis classification

Revision ID: 0008_add_hemolysis_classification
Revises: 0007_remove_legacy_status
Create Date: 2026-03-15 12:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_add_hemolysis_classification"
down_revision = "0007_remove_legacy_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("samples", sa.Column("hemolysis_classification", sa.Integer(), nullable=True))
    op.create_index("ix_samples_hemolysis_classification", "samples", ["hemolysis_classification"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_samples_hemolysis_classification", table_name="samples")
    op.drop_column("samples", "hemolysis_classification")
