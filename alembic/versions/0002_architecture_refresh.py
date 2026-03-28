"""architecture refresh

Revision ID: 0002_architecture_refresh
Revises: 0001_initial
Create Date: 2026-03-09 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_architecture_refresh"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

user_role_enum = sa.Enum("admin", "staff", name="userrole")


def upgrade() -> None:
    bind = op.get_bind()
    user_role_enum.create(bind, checkfirst=True)

    op.add_column(
        "users",
        sa.Column("role", user_role_enum, nullable=False, server_default="staff"),
    )
    op.add_column("sample_types", sa.Column("field_schema_json", sa.Text(), nullable=True))
    op.add_column("samples", sa.Column("metadata_json", sa.Text(), nullable=True))

    op.create_index("ix_samples_name", "samples", ["name"], unique=False)
    op.create_index("ix_samples_status", "samples", ["status"], unique=False)
    op.create_index("ix_samples_sample_type_id", "samples", ["sample_type_id"], unique=False)
    op.create_index("ix_samples_updated_at", "samples", ["updated_at"], unique=False)
    op.create_index("ix_events_user_id", "events", ["user_id"], unique=False)
    op.create_index("ix_events_sample_id", "events", ["sample_id"], unique=False)
    op.create_index("ix_events_created_at", "events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_events_created_at", table_name="events")
    op.drop_index("ix_events_sample_id", table_name="events")
    op.drop_index("ix_events_user_id", table_name="events")
    op.drop_index("ix_samples_updated_at", table_name="samples")
    op.drop_index("ix_samples_sample_type_id", table_name="samples")
    op.drop_index("ix_samples_status", table_name="samples")
    op.drop_index("ix_samples_name", table_name="samples")

    op.drop_column("samples", "metadata_json")
    op.drop_column("sample_types", "field_schema_json")
    op.drop_column("users", "role")

    bind = op.get_bind()
    user_role_enum.drop(bind, checkfirst=True)
