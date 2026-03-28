"""sample metadata refresh

Revision ID: 0005_sample_metadata_refresh
Revises: 0004_storage_notes
Create Date: 2026-03-09 02:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_sample_metadata_refresh"
down_revision = "0004_storage_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_studies_code", "studies", ["code"], unique=True)

    op.create_table(
        "sample_note_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sample_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_sample_note_entries_sample_id", "sample_note_entries", ["sample_id"], unique=False)
    op.create_index("ix_sample_note_entries_user_id", "sample_note_entries", ["user_id"], unique=False)
    op.create_index("ix_sample_note_entries_created_at", "sample_note_entries", ["created_at"], unique=False)

    op.add_column("samples", sa.Column("state", sa.String(length=50), nullable=False, server_default="available"))
    op.add_column("samples", sa.Column("study_id", sa.Integer(), nullable=True))
    op.add_column("samples", sa.Column("visit_label", sa.String(length=30), nullable=True))
    op.add_column("samples", sa.Column("timepoint_label", sa.String(length=30), nullable=True))
    op.add_column("samples", sa.Column("aliquot_number", sa.Integer(), nullable=True))
    op.add_column("samples", sa.Column("thaw_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("samples", sa.Column("collection_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_samples_state", "samples", ["state"], unique=False)
    op.create_index("ix_samples_study_id", "samples", ["study_id"], unique=False)
    op.create_index("ix_samples_visit_label", "samples", ["visit_label"], unique=False)
    op.create_index("ix_samples_timepoint_label", "samples", ["timepoint_label"], unique=False)
    op.create_index("ix_samples_aliquot_number", "samples", ["aliquot_number"], unique=False)
    op.create_index("ix_samples_collection_at", "samples", ["collection_at"], unique=False)

    op.execute(
        sa.text(
            """
            UPDATE samples
            SET state = CASE
                WHEN status IN ('consumed', 'archived', 'retrieved') THEN 'archived'
                ELSE 'available'
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_samples_collection_at", table_name="samples")
    op.drop_index("ix_samples_aliquot_number", table_name="samples")
    op.drop_index("ix_samples_timepoint_label", table_name="samples")
    op.drop_index("ix_samples_visit_label", table_name="samples")
    op.drop_index("ix_samples_study_id", table_name="samples")
    op.drop_index("ix_samples_state", table_name="samples")

    op.drop_column("samples", "collection_at")
    op.drop_column("samples", "thaw_count")
    op.drop_column("samples", "aliquot_number")
    op.drop_column("samples", "timepoint_label")
    op.drop_column("samples", "visit_label")
    op.drop_column("samples", "study_id")
    op.drop_column("samples", "state")

    op.drop_index("ix_sample_note_entries_created_at", table_name="sample_note_entries")
    op.drop_index("ix_sample_note_entries_user_id", table_name="sample_note_entries")
    op.drop_index("ix_sample_note_entries_sample_id", table_name="sample_note_entries")
    op.drop_table("sample_note_entries")

    op.drop_index("ix_studies_code", table_name="studies")
    op.drop_table("studies")
