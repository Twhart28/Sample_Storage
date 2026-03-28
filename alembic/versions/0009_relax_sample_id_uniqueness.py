"""relax sample id uniqueness

Revision ID: 0009_relax_sample_id_uniqueness
Revises: 0008_add_hemolysis_classification
Create Date: 2026-03-16 09:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_relax_sample_id_uniqueness"
down_revision = "0008_add_hemolysis_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("samples", recreate="always") as batch_op:
        batch_op.alter_column(
            "sample_id",
            existing_type=sa.String(length=50),
            nullable=False,
            unique=False,
        )
        batch_op.create_index("ix_samples_sample_id", ["sample_id"], unique=False)
        batch_op.create_index(
            "ix_samples_identity_lookup",
            ["sample_id", "sample_type_id", "visit_label", "timepoint_label", "aliquot_number"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("samples", recreate="always") as batch_op:
        batch_op.drop_index("ix_samples_identity_lookup")
        batch_op.drop_index("ix_samples_sample_id")
        batch_op.alter_column(
            "sample_id",
            existing_type=sa.String(length=50),
            nullable=False,
            unique=True,
        )
