"""remove legacy fields

Revision ID: 0006_remove_legacy_fields
Revises: 0005_sample_metadata_refresh
Create Date: 2026-03-15 11:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_remove_legacy_fields"
down_revision = "0005_sample_metadata_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("samples") as batch_op:
        batch_op.drop_index("ix_samples_name")
        batch_op.drop_column("name")
        batch_op.drop_column("metadata_json")

    with op.batch_alter_table("sample_types") as batch_op:
        batch_op.drop_column("field_schema_json")

    with op.batch_alter_table("studies") as batch_op:
        batch_op.drop_index("ix_studies_code")
        batch_op.drop_column("code")


def downgrade() -> None:
    with op.batch_alter_table("studies") as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(length=50), nullable=True))
        batch_op.create_index("ix_studies_code", ["code"], unique=True)

    with op.batch_alter_table("sample_types") as batch_op:
        batch_op.add_column(sa.Column("field_schema_json", sa.Text(), nullable=True))

    with op.batch_alter_table("samples") as batch_op:
        batch_op.add_column(sa.Column("metadata_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("name", sa.String(length=100), nullable=True))
        batch_op.create_index("ix_samples_name", ["name"], unique=False)
