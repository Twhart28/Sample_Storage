"""rebuild samples without unique sample id

Revision ID: 0010_rebuild_samples_without_unique_sample_id
Revises: 0009_relax_sample_id_uniqueness
Create Date: 2026-03-16 09:20:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "0010_rebuild_samples_without_unique_sample_id"
down_revision = "0009_relax_sample_id_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute(
        """
        CREATE TABLE samples_new (
            id INTEGER NOT NULL PRIMARY KEY,
            sample_id VARCHAR(50) NOT NULL,
            volume FLOAT,
            volume_units VARCHAR(20),
            sample_type_id INTEGER,
            notes TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            state VARCHAR(50) DEFAULT 'available' NOT NULL,
            study_id INTEGER,
            visit_label VARCHAR(30),
            timepoint_label VARCHAR(30),
            aliquot_number INTEGER,
            thaw_count INTEGER DEFAULT '0' NOT NULL,
            collection_at DATETIME,
            hemolysis_classification INTEGER,
            FOREIGN KEY(sample_type_id) REFERENCES sample_types (id),
            FOREIGN KEY(study_id) REFERENCES studies (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO samples_new (
            id, sample_id, volume, volume_units, sample_type_id, notes,
            created_at, updated_at, state, study_id, visit_label,
            timepoint_label, aliquot_number, thaw_count, collection_at,
            hemolysis_classification
        )
        SELECT
            id, sample_id, volume, volume_units, sample_type_id, notes,
            created_at, updated_at, state, study_id, visit_label,
            timepoint_label, aliquot_number, thaw_count, collection_at,
            hemolysis_classification
        FROM samples
        """
    )
    op.execute("DROP TABLE samples")
    op.execute("ALTER TABLE samples_new RENAME TO samples")
    op.create_index("ix_samples_sample_id", "samples", ["sample_id"], unique=False)
    op.create_index(
        "ix_samples_identity_lookup",
        "samples",
        ["sample_id", "sample_type_id", "visit_label", "timepoint_label", "aliquot_number"],
        unique=False,
    )
    op.create_index("ix_samples_sample_type_id", "samples", ["sample_type_id"], unique=False)
    op.create_index("ix_samples_state", "samples", ["state"], unique=False)
    op.create_index("ix_samples_study_id", "samples", ["study_id"], unique=False)
    op.create_index("ix_samples_visit_label", "samples", ["visit_label"], unique=False)
    op.create_index("ix_samples_timepoint_label", "samples", ["timepoint_label"], unique=False)
    op.create_index("ix_samples_aliquot_number", "samples", ["aliquot_number"], unique=False)
    op.create_index("ix_samples_collection_at", "samples", ["collection_at"], unique=False)
    op.create_index("ix_samples_hemolysis_classification", "samples", ["hemolysis_classification"], unique=False)
    op.create_index("ix_samples_updated_at", "samples", ["updated_at"], unique=False)
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute(
        """
        CREATE TABLE samples_old (
            id INTEGER NOT NULL PRIMARY KEY,
            sample_id VARCHAR(50) NOT NULL UNIQUE,
            volume FLOAT,
            volume_units VARCHAR(20),
            sample_type_id INTEGER,
            notes TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            state VARCHAR(50) DEFAULT 'available' NOT NULL,
            study_id INTEGER,
            visit_label VARCHAR(30),
            timepoint_label VARCHAR(30),
            aliquot_number INTEGER,
            thaw_count INTEGER DEFAULT '0' NOT NULL,
            collection_at DATETIME,
            hemolysis_classification INTEGER,
            FOREIGN KEY(sample_type_id) REFERENCES sample_types (id),
            FOREIGN KEY(study_id) REFERENCES studies (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO samples_old (
            id, sample_id, volume, volume_units, sample_type_id, notes,
            created_at, updated_at, state, study_id, visit_label,
            timepoint_label, aliquot_number, thaw_count, collection_at,
            hemolysis_classification
        )
        SELECT
            id, sample_id, volume, volume_units, sample_type_id, notes,
            created_at, updated_at, state, study_id, visit_label,
            timepoint_label, aliquot_number, thaw_count, collection_at,
            hemolysis_classification
        FROM samples
        """
    )
    op.execute("DROP TABLE samples")
    op.execute("ALTER TABLE samples_old RENAME TO samples")
    op.create_index("ix_samples_sample_type_id", "samples", ["sample_type_id"], unique=False)
    op.create_index("ix_samples_state", "samples", ["state"], unique=False)
    op.create_index("ix_samples_study_id", "samples", ["study_id"], unique=False)
    op.create_index("ix_samples_visit_label", "samples", ["visit_label"], unique=False)
    op.create_index("ix_samples_timepoint_label", "samples", ["timepoint_label"], unique=False)
    op.create_index("ix_samples_aliquot_number", "samples", ["aliquot_number"], unique=False)
    op.create_index("ix_samples_collection_at", "samples", ["collection_at"], unique=False)
    op.create_index("ix_samples_hemolysis_classification", "samples", ["hemolysis_classification"], unique=False)
    op.create_index("ix_samples_updated_at", "samples", ["updated_at"], unique=False)
    op.execute("PRAGMA foreign_keys=ON")
