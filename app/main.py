from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.api.routes import events as api_events
from app.api.routes import exports as api_exports
from app.api.routes import analyses as api_analyses
from app.api.routes import samples as api_samples
from app.api.routes import storage as api_storage
from app.domain.models import Base
from app.web.routes import admin, analyses, auth, dashboard, events, samples, settings, storage, visit_workflows


def _ensure_schema_compatibility() -> None:
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if "samples" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("samples")}
    with db.engine.begin() as conn:
        if "study_role" not in columns:
            conn.execute(text("ALTER TABLE samples ADD COLUMN study_role VARCHAR(50) NOT NULL DEFAULT 'current'"))
        if "is_archived" not in columns:
            conn.execute(text("ALTER TABLE samples ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0"))
        if "is_out_for_analysis" not in columns:
            conn.execute(text("ALTER TABLE samples ADD COLUMN is_out_for_analysis BOOLEAN NOT NULL DEFAULT 0"))

        refreshed_columns = {column["name"] for column in inspect(conn).get_columns("samples")}
        conn.execute(
            text(
                """
                UPDATE samples
                SET
                    study_role = COALESCE(NULLIF(study_role, ''), 'current'),
                    is_archived = COALESCE(is_archived, 0),
                    is_out_for_analysis = COALESCE(is_out_for_analysis, 0)
                """
            )
        )
        if "state" in refreshed_columns:
            conn.execute(
                text(
                    """
                    UPDATE samples
                    SET
                        study_role = 'current',
                        is_archived = CASE WHEN state = 'archived' THEN 1 ELSE 0 END,
                        is_out_for_analysis = 0
                    """
                )
            )
        if "sample_locations" in table_names:
            conn.execute(
                text(
                    """
                    DELETE FROM sample_locations
                    WHERE sample_id IN (
                        SELECT id FROM samples WHERE is_archived = 1
                    )
                    """
                )
            )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_samples_study_role ON samples (study_role)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_samples_is_archived ON samples (is_archived)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_samples_is_out_for_analysis ON samples (is_out_for_analysis)"))

        if "study_workflows" in table_names:
            workflow_columns = {column["name"] for column in inspect(conn).get_columns("study_workflows")}
            if "template_workbook_filename" not in workflow_columns:
                conn.execute(text("ALTER TABLE study_workflows ADD COLUMN template_workbook_filename VARCHAR(255)"))
            if "template_workbook_blob" not in workflow_columns:
                conn.execute(text("ALTER TABLE study_workflows ADD COLUMN template_workbook_blob BLOB"))


def create_app() -> FastAPI:
    app = FastAPI(title="Freezer Sample Tracker")
    _ensure_schema_compatibility()
    Base.metadata.create_all(bind=db.engine)
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("SESSION_SECRET", "dev-secret-key"),
    )
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(analyses.router)
    app.include_router(samples.router)
    app.include_router(storage.router)
    app.include_router(events.router)
    app.include_router(settings.router)
    app.include_router(admin.router)
    app.include_router(visit_workflows.router)

    app.include_router(api_samples.router)
    app.include_router(api_analyses.router)
    app.include_router(api_storage.router)
    app.include_router(api_events.router)
    app.include_router(api_exports.router)
    return app


app = create_app()
