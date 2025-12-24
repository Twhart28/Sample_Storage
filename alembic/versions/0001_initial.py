"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sample_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=True),
    )
    op.create_table(
        "storage_nodes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "node_type",
            sa.Enum("freezer", "shelf", "rack", "box", name="storagenodetype"),
            nullable=False,
        ),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("storage_nodes.id")),
    )
    op.create_table(
        "samples",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sample_id", sa.String(length=50), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100)),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("volume", sa.Float),
        sa.Column("volume_units", sa.String(length=20)),
        sa.Column("sample_type_id", sa.Integer, sa.ForeignKey("sample_types.id")),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "storage_positions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("box_id", sa.Integer, sa.ForeignKey("storage_nodes.id")),
        sa.Column("row", sa.Integer, nullable=False),
        sa.Column("col", sa.Integer, nullable=False),
        sa.Column("label", sa.String(length=10), nullable=False),
        sa.UniqueConstraint("box_id", "row", "col", name="uq_box_row_col"),
    )
    op.create_table(
        "sample_locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sample_id", sa.Integer, sa.ForeignKey("samples.id"), unique=True),
        sa.Column(
            "position_id",
            sa.Integer,
            sa.ForeignKey("storage_positions.id"),
            unique=True,
        ),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "event_type",
            sa.Enum(
                "create_sample",
                "update_sample",
                "place_sample",
                "move_sample",
                "status_change",
                "create_storage",
                name="eventtype",
            ),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("sample_id", sa.Integer, sa.ForeignKey("samples.id")),
        sa.Column("from_position_id", sa.Integer, sa.ForeignKey("storage_positions.id")),
        sa.Column("to_position_id", sa.Integer, sa.ForeignKey("storage_positions.id")),
        sa.Column("payload_json", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("sample_locations")
    op.drop_table("storage_positions")
    op.drop_table("samples")
    op.drop_table("storage_nodes")
    op.drop_table("sample_types")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS eventtype")
    op.execute("DROP TYPE IF EXISTS storagenodetype")
