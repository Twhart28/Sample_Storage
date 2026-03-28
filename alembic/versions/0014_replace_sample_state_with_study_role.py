"""replace sample state with study role

Revision ID: 0014_replace_sample_state_with_study_role
Revises: 0013_make_analysis_batch_header_optional
Create Date: 2026-03-28 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_replace_sample_state_with_study_role"
down_revision = "0013_make_analysis_batch_header_optional"
branch_labels = None
depends_on = None


study_role_enum = sa.Enum("current", "retired", name="studyrole")


def upgrade() -> None:
    with op.batch_alter_table("samples") as batch_op:
        batch_op.add_column(sa.Column("study_role", study_role_enum, nullable=True, server_default="current"))
        batch_op.add_column(sa.Column("is_archived", sa.Boolean(), nullable=True, server_default=sa.false()))
        batch_op.add_column(sa.Column("is_out_for_analysis", sa.Boolean(), nullable=True, server_default=sa.false()))

    op.execute(
        sa.text(
            """
            UPDATE samples
            SET
                study_role = 'current',
                is_archived = CASE WHEN state = 'archived' THEN 1 ELSE 0 END,
                is_out_for_analysis = 0
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM sample_locations
            WHERE sample_id IN (
                SELECT id FROM samples WHERE is_archived = 1
            )
            """
        )
    )

    with op.batch_alter_table("samples") as batch_op:
        batch_op.alter_column("study_role", existing_type=study_role_enum, nullable=False, server_default="current")
        batch_op.alter_column("is_archived", existing_type=sa.Boolean(), nullable=False, server_default=sa.false())
        batch_op.alter_column("is_out_for_analysis", existing_type=sa.Boolean(), nullable=False, server_default=sa.false())
        batch_op.drop_column("state")
        batch_op.create_index("ix_samples_study_role", ["study_role"], unique=False)
        batch_op.create_index("ix_samples_is_archived", ["is_archived"], unique=False)
        batch_op.create_index("ix_samples_is_out_for_analysis", ["is_out_for_analysis"], unique=False)


def downgrade() -> None:
    sample_state_enum = sa.Enum("available", "partially_used", "archived", name="samplestate")

    with op.batch_alter_table("samples") as batch_op:
        batch_op.add_column(sa.Column("state", sample_state_enum, nullable=True, server_default="available"))

    op.execute(
        sa.text(
            """
            UPDATE samples
            SET state = CASE
                WHEN is_archived = 1 THEN 'archived'
                WHEN thaw_count > 0 THEN 'partially_used'
                ELSE 'available'
            END
            """
        )
    )

    with op.batch_alter_table("samples") as batch_op:
        batch_op.alter_column("state", existing_type=sample_state_enum, nullable=False, server_default="available")
        batch_op.drop_index("ix_samples_is_out_for_analysis")
        batch_op.drop_index("ix_samples_is_archived")
        batch_op.drop_index("ix_samples_study_role")
        batch_op.drop_column("is_out_for_analysis")
        batch_op.drop_column("is_archived")
        batch_op.drop_column("study_role")
