from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional dev dependency in this environment
    TestClient = None

from sqlalchemy.orm import close_all_sessions

from app import db
from app.domain import models
from app.domain.models import Base
from app.main import create_app
from app.schemas import (
    BoxCreateInput,
    PlaceSampleInput,
    SampleCreateInput,
    SampleTypeCreate,
    StorageNodeCreate,
    StudyWorkflowConfigInput,
    StudyCreate,
)
from app.services import admin as admin_service
from app.services import analyses as analysis_service
from app.services import auth as auth_service
from app.services import batch_modify as batch_modify_service
from app.services import samples as sample_service
from app.services import storage as storage_service
from app.services import visit_workflows as visit_service


@unittest.skipIf(TestClient is None, "fastapi testclient dependencies are not installed")
class RouteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tempdir.name, "route-tests.db").resolve().as_posix()
        db.configure(f"sqlite:///{db_path}")
        Base.metadata.drop_all(bind=db.engine)
        Base.metadata.create_all(bind=db.engine)
        self.client = TestClient(create_app())

    def tearDown(self):
        close_all_sessions()
        db.engine.dispose()
        self.tempdir.cleanup()

    def seed_analysis_sample(self, sample_identifier: str = "AN-ROUTE-1"):
        session = db.SessionLocal()
        try:
            admin_user = auth_service.sync_user(session, "admin", "Admin User")
            study = admin_service.create_study(session, StudyCreate(name="Route Study"))
            sample_type = admin_service.create_sample_type(session, SampleTypeCreate(name="Plasma", description="Plasma"))
            freezer = storage_service.create_storage_node(
                session,
                StorageNodeCreate(name="Route Freezer", node_type="freezer"),
                admin_user,
            )
            shelf = storage_service.create_storage_node(
                session,
                StorageNodeCreate(name="Shelf A", node_type="shelf", parent_id=freezer.id),
                admin_user,
            )
            box = storage_service.create_storage_node(
                session,
                StorageNodeCreate(name="Route Box", node_type="box", parent_id=shelf.id),
                admin_user,
            )
            storage_service.create_box_positions(
                session,
                BoxCreateInput(box_id=box.id, rows=2, cols=2),
                admin_user,
            )
            position_id = storage_service.get_box_view(session, box.id).positions[0].id
            sample = sample_service.create_sample(
                session,
                SampleCreateInput(
                    sample_id=sample_identifier,
                    sample_type_id=sample_type.id,
                    study_id=study.id,
                    volume=1.0,
                ),
                admin_user,
            )
            sample_service.place_sample(
                session,
                sample.id,
                PlaceSampleInput(position_id=position_id),
                admin_user,
            )
            return sample.id, position_id
        finally:
            session.close()

    def test_staff_cannot_create_storage_node(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        self.client.post(
            "/login",
            data={"username": "staffer", "full_name": "Staff User"},
        )
        settings_page = self.client.get("/settings")
        self.assertEqual(settings_page.status_code, 200)
        self.assertContains(settings_page, "Workspace Settings")
        self.assertContains(settings_page, "Account")

        response = self.client.post(
            "/api/storage/node",
            json={"name": "Freezer A", "node_type": "freezer", "parent_id": None},
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_manage_metadata_and_search_sample(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        admin_page = self.client.get("/settings")
        self.assertEqual(admin_page.status_code, 200)
        self.assertContains(admin_page, "Sample Types")
        self.assertContains(admin_page, "Studies")

        sample_type = self.client.post(
            "/admin/sample-types",
            data={"name": "Plasma", "description": "Plasma"},
            follow_redirects=False,
        )
        self.assertEqual(sample_type.status_code, 303)

        study = self.client.post(
            "/admin/studies",
            data={"name": "Sovary", "description": "Study"},
            follow_redirects=False,
        )
        self.assertEqual(study.status_code, 303)

        freezer = self.client.post(
            "/api/storage/node",
            json={"name": "Freezer A", "node_type": "freezer", "parent_id": None},
        )
        self.assertEqual(freezer.status_code, 200)

        studies_page = self.client.get("/settings/studies")
        self.assertContains(studies_page, "Sovary")
        sample_types_page = self.client.get("/settings/sample-types")
        self.assertContains(sample_types_page, "Plasma")

        created = self.client.post(
            "/api/samples/",
            json={
                "sample_id": "SOV21-V1-T60",
                "sample_type_id": 1,
                "study_id": 1,
                "visit_label": "1",
                "timepoint_label": "60",
                "thaw_count": 0,
                "notes": "Baseline",
            },
        )
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertEqual(payload["sample_id"], "SOV21-V1-T60")
        self.assertEqual(payload["study_name"], "Sovary")

        note = self.client.post(
            f"/api/samples/{payload['id']}/notes",
            json={"text": "Used 0.2 mL"},
        )
        self.assertEqual(note.status_code, 200)
        self.assertEqual(note.json()["note_entries"][0]["text"], "Used 0.2 mL")

        listing = self.client.get("/api/samples/", params={"study_id": 1, "visit_label": "1", "q": "T60"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)
        self.assertEqual(listing.json()[0]["sample_id"], "SOV21-V1-T60")

        blocked_delete_type = self.client.post("/admin/sample-types/1/delete", follow_redirects=True)
        self.assertEqual(blocked_delete_type.status_code, 400)
        self.assertContains(blocked_delete_type, "cannot be deleted while samples still reference it")

        blocked_delete_study = self.client.post("/admin/studies/1/delete", follow_redirects=True)
        self.assertEqual(blocked_delete_study.status_code, 400)
        self.assertContains(blocked_delete_study, "cannot be deleted while samples still reference it")

        disposable_type = self.client.post(
            "/admin/sample-types",
            data={"name": "Serum", "description": "Disposable"},
            follow_redirects=False,
        )
        self.assertEqual(disposable_type.status_code, 303)
        delete_disposable_type = self.client.post("/admin/sample-types/2/delete", follow_redirects=False)
        self.assertEqual(delete_disposable_type.status_code, 303)

        disposable_study = self.client.post(
            "/admin/studies",
            data={"name": "NRS", "description": "Disposable"},
            follow_redirects=False,
        )
        self.assertEqual(disposable_study.status_code, 303)
        delete_disposable_study = self.client.post("/admin/studies/2/delete", follow_redirects=False)
        self.assertEqual(delete_disposable_study.status_code, 303)

    def test_admin_can_delete_sample_but_staff_cannot(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        self.client.post(
            "/admin/sample-types",
            data={"name": "Plasma", "description": "Plasma"},
            follow_redirects=False,
        )
        created = self.client.post(
            "/api/samples/",
            json={
                "sample_id": "DELETE-ME",
                "sample_type_id": 1,
                "thaw_count": 0,
            },
        )
        self.assertEqual(created.status_code, 200)
        sample_id = created.json()["id"]

        deleted = self.client.delete(f"/api/samples/{sample_id}")
        self.assertEqual(deleted.status_code, 200)
        missing = self.client.get(f"/api/samples/{sample_id}")
        self.assertEqual(missing.status_code, 404)

        self.client.post(
            "/login",
            data={"username": "staffer", "full_name": "Staff User"},
        )
        created_again = self.client.post(
            "/api/samples/",
            json={
                "sample_id": "DELETE-NO",
                "sample_type_id": 1,
                "thaw_count": 0,
            },
        )
        self.assertEqual(created_again.status_code, 200)
        forbidden = self.client.delete(f"/api/samples/{created_again.json()['id']}")
        self.assertEqual(forbidden.status_code, 403)

    def test_analysis_workspace_download_preview_and_commit(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        sample_id, _position_id = self.seed_analysis_sample()

        samples_page = self.client.get("/samples")
        self.assertEqual(samples_page.status_code, 200)
        self.assertContains(samples_page, "Select")

        detail_page = self.client.get(f"/samples/{sample_id}")
        self.assertEqual(detail_page.status_code, 200)
        self.assertContains(detail_page, "Add to selection")

        generic_workspace = self.client.get("/sample-actions", params={"sample_ids": sample_id})
        self.assertEqual(generic_workspace.status_code, 200)
        self.assertContains(generic_workspace, "Sample Actions")
        self.assertContains(generic_workspace, "Batch Analyze")
        self.assertContains(generic_workspace, "Batch Modify")

        workspace = self.client.get("/sample-actions/analyze", params={"sample_ids": sample_id})
        self.assertEqual(workspace.status_code, 200)
        self.assertContains(workspace, "Batch Analyze")
        self.assertContains(workspace, "Generate analysis log")

        workbook = self.client.get("/sample-actions/analyze/log", params={"sample_ids": sample_id})
        self.assertEqual(workbook.status_code, 200)
        self.assertEqual(
            workbook.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        preview = self.client.post(
            "/sample-actions/analyze/preview",
            files={"analysis_file": ("analysis-log.xlsx", workbook.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Preview")
        self.assertContains(preview, "valid /")

        raw_payload = analysis_service.analysis_workbook_to_payload(workbook.content)
        commit = self.client.post("/sample-actions/analyze/commit", data={"raw_payload": raw_payload})
        self.assertEqual(commit.status_code, 200)
        self.assertContains(commit, "Commit Result")

        updated = self.client.get(f"/api/samples/{sample_id}")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["study_role"], "current")
        self.assertEqual(updated.json()["custody_label"], "in storage")
        self.assertEqual(updated.json()["usage_label"], "used")
        self.assertEqual(updated.json()["thaw_count"], 1)
        self.assertEqual(updated.json()["volume"], 1.0)

    def test_batch_modify_workspace_download_preview_and_commit(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        sample_id, _position_id = self.seed_analysis_sample("MOD-ROUTE-1")

        workspace = self.client.get("/sample-actions/modify", params={"sample_ids": sample_id})
        self.assertEqual(workspace.status_code, 200)
        self.assertContains(workspace, "Batch Modify")
        self.assertContains(workspace, "Generate modify log")

        workbook = self.client.get("/sample-actions/modify/log", params={"sample_ids": sample_id})
        self.assertEqual(workbook.status_code, 200)
        self.assertEqual(
            workbook.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        raw_payload = batch_modify_service.modify_workbook_to_payload(workbook.content)
        preview = self.client.post(
            "/sample-actions/modify/preview",
            files={"modify_file": ("batch-modify.xlsx", workbook.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Commit Batch Modify")

        commit = self.client.post("/sample-actions/modify/commit", data={"raw_payload": raw_payload})
        self.assertEqual(commit.status_code, 200)
        self.assertContains(commit, "Commit Result")

        updated = self.client.get(f"/api/samples/{sample_id}")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["study_role"], "current")
        self.assertEqual(updated.json()["custody_label"], "in storage")
        self.assertEqual(updated.json()["usage_label"], "unused")

    def test_dashboard_and_visit_workflow_pages_render(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        session = db.SessionLocal()
        try:
            admin_user = auth_service.sync_user(session, "admin", "Admin User")
            study = admin_service.create_study(session, StudyCreate(name="Visit Study"))
            visit_service.save_workflow_config(
                session,
                study.id,
                StudyWorkflowConfigInput(
                    label="Visit Workflow",
                    description="Visit execution",
                    is_active=True,
                    quick_links=[
                        {"label": "Biochem / Lipid Results", "url": "https://example.com/biochem.xlsx"},
                        {"label": "Dilution Calculator", "url": "https://example.com/dilution.xlsx"},
                    ],
                ),
            )
        finally:
            session.close()

        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Study Workflows")
        self.assertContains(dashboard, "Start visit workflow")

        workspace = self.client.get("/visit-workflows")
        self.assertEqual(workspace.status_code, 200)
        self.assertContains(workspace, "Visit Execution")
        self.assertContains(workspace, "Visit Study")

    def test_visit_workflow_start_preview_commit_and_summary(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        session = db.SessionLocal()
        try:
            admin_user = auth_service.sync_user(session, "admin", "Admin User")
            study = admin_service.create_study(session, StudyCreate(name="Visit Study"))
            sample_type = admin_service.create_sample_type(session, SampleTypeCreate(name="Plasma", description="Plasma"))
            freezer = storage_service.create_storage_node(session, StorageNodeCreate(name="Visit Freezer", node_type="freezer"), admin_user)
            shelf = storage_service.create_storage_node(session, StorageNodeCreate(name="Visit Shelf", node_type="shelf", parent_id=freezer.id), admin_user)
            rack = storage_service.create_storage_node(session, StorageNodeCreate(name="Visit Rack", node_type="rack", parent_id=shelf.id), admin_user)
            box = storage_service.create_storage_node(session, StorageNodeCreate(name="Visit Box", node_type="box", parent_id=rack.id), admin_user)
            storage_service.create_box_positions(session, BoxCreateInput(box_id=box.id, rows=2, cols=2), admin_user)
            self.assertIsNotNone(sample_type)
            visit_service.save_workflow_config(
                session,
                study.id,
                StudyWorkflowConfigInput(
                    label="Visit Workflow",
                    description="Visit execution",
                    is_active=True,
                    quick_links=[
                        {"label": "Biochem / Lipid Results", "url": "https://example.com/biochem.xlsx"},
                        {"label": "Dilution Calculator", "url": "https://example.com/dilution.xlsx"},
                    ],
                ),
            )
        finally:
            session.close()

        started = self.client.post(
            "/visit-workflows",
            data={"study_id": "1", "participant_id": "PT-ROUTE-1", "visit_date": "2026-03-28T09:00"},
            follow_redirects=False,
        )
        self.assertEqual(started.status_code, 303)
        session_url = started.headers["location"]

        detail = self.client.get(session_url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Download visit template")
        self.assertContains(detail, "Biochem / Lipid Results")

        workbook = self.client.get(f"{session_url}/template")
        self.assertEqual(workbook.status_code, 200)
        modified = load_workbook(filename=BytesIO(workbook.content))
        modified["sample_Import"]["A2"] = "VR-001"
        modified["sample_Import"]["B2"] = "Plasma"
        modified["sample_Import"]["F2"] = 1
        modified["sample_Import"]["I2"] = 1.0
        modified["sample_Import"]["K2"] = 0
        modified["sample_Import"]["M2"] = "03/28/26 09:10"
        modified["sample_Import"]["N2"] = "specific"
        modified["sample_Import"]["O2"] = "Visit Box"
        modified["sample_Import"]["P2"] = "A1"
        buffer = BytesIO()
        modified.save(buffer)

        preview = self.client.post(
            f"{session_url}/preview",
            files={"visit_file": ("visit-session.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Preview")
        self.assertContains(preview, "VR-001")

        raw_payload = visit_service.visit_workbook_to_payload(buffer.getvalue(), uploaded_filename="visit-session.xlsx")
        commit = self.client.post(
            f"{session_url}/commit",
            data={"raw_payload": raw_payload, "uploaded_filename": "visit-session.xlsx"},
        )
        self.assertEqual(commit.status_code, 200)
        self.assertContains(commit, "Commit Result")

        summary = self.client.get(f"{session_url}/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertContains(summary, "Visit Summary")
        self.assertContains(summary, "VR-001")

    def test_user_without_process_analysis_permission_is_blocked(self):
        self.client.post(
            "/login",
            data={"username": "admin", "full_name": "Admin User"},
        )
        sample_id, _position_id = self.seed_analysis_sample("AN-NOAUTH")

        session = db.SessionLocal()
        try:
            admin_user = auth_service.sync_user(session, "admin", "Admin User")
            limited_user = auth_service.sync_user(session, "limited", "Limited User")
            auth_service.update_user_admin(
                session,
                admin_user,
                limited_user.id,
                full_name="Limited User",
                role="staff",
                permissions=["edit_samples", "archive_samples", "place_move_samples", "bulk_import_samples"],
            )
        finally:
            session.close()

        self.client.post(
            "/login",
            data={"username": "limited", "full_name": "Limited User"},
        )

        generic_workspace = self.client.get("/sample-actions", params={"sample_ids": sample_id})
        self.assertEqual(generic_workspace.status_code, 200)
        self.assertContains(generic_workspace, "Batch Modify")
        self.assertNotContains(generic_workspace, "Batch Analyze")

        workspace = self.client.get("/analyses", params={"sample_ids": sample_id})
        self.assertEqual(workspace.status_code, 403)

        download = self.client.get("/analyses/log", params={"sample_ids": sample_id})
        self.assertEqual(download.status_code, 403)

        preview = self.client.post("/analyses/preview", data={})
        self.assertEqual(preview.status_code, 403)

        commit = self.client.post("/analyses/commit", data={"raw_payload": "{}"})
        self.assertEqual(commit.status_code, 403)

    def assertNotContains(self, response, text):
        self.assertNotIn(text, response.text)

    def assertContains(self, response, text):
        self.assertIn(text, response.text)


if __name__ == "__main__":
    unittest.main()
