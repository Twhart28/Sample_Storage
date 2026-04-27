"""add rack layout slots

Revision ID: 0016_add_rack_layout_slots
Revises: 0015_add_visit_workflows
Create Date: 2026-04-22 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_add_rack_layout_slots"
down_revision = "0015_add_visit_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("storage_nodes", sa.Column("rack_rows", sa.Integer(), nullable=True))
    op.add_column("storage_nodes", sa.Column("rack_cols", sa.Integer(), nullable=True))
    op.add_column("storage_nodes", sa.Column("rack_slot_row", sa.Integer(), nullable=True))
    op.add_column("storage_nodes", sa.Column("rack_slot_col", sa.Integer(), nullable=True))
    op.create_index(
        "uq_storage_sibling_rack_slot",
        "storage_nodes",
        ["parent_id", "rack_slot_row", "rack_slot_col"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_storage_sibling_rack_slot", table_name="storage_nodes")
    op.drop_column("storage_nodes", "rack_slot_col")
    op.drop_column("storage_nodes", "rack_slot_row")
    op.drop_column("storage_nodes", "rack_cols")
    op.drop_column("storage_nodes", "rack_rows")
