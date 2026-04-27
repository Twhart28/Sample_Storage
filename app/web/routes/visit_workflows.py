from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    StudyWorkflowConfigInput,
    VisitSessionCompleteInput,
    VisitSessionCreateInput,
    VisitSessionNotesInput,
    StudyWorkflowQuickLinkInput,
)
from app.services import admin as admin_service
from app.services import visit_workflows as visit_service
from app.web.dependencies import require_current_user, require_permission, templates

router = APIRouter()


@router.get("/visit-workflows")
async def visit_workflow_index(request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    return _render_index(request, db, current_user=current_user)


@router.post("/visit-workflows")
async def start_visit_workflow(request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    form = await request.form()
    try:
        session = visit_service.create_visit_session(
            db,
            VisitSessionCreateInput(
                study_id=int(str(form.get("study_id") or "0")),
                participant_id=str(form.get("participant_id") or ""),
                visit_date=_parse_datetime(str(form.get("visit_date") or "")),
            ),
            current_user,
        )
    except (ValueError, visit_service.VisitWorkflowError) as exc:
        return _render_index(
            request,
            db,
            current_user=current_user,
            error_message=str(exc),
            initial_values={
                "study_id": str(form.get("study_id") or ""),
                "participant_id": str(form.get("participant_id") or ""),
                "visit_date": str(form.get("visit_date") or ""),
            },
            status_code=400,
        )
    return RedirectResponse(f"/visit-workflows/{session.id}", status_code=303)


@router.get("/visit-workflows/{session_id}")
async def visit_workflow_detail(session_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    try:
        session = visit_service.get_visit_session(db, session_id)
    except visit_service.VisitWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_session_page(request, db=db, current_user=current_user, session=session)


@router.get("/visit-workflows/{session_id}/template")
async def visit_workflow_template(session_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    try:
        filename, workbook = visit_service.generate_visit_template_xlsx(db, session_id)
    except visit_service.VisitWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/visit-workflows/{session_id}/open-link/{link_key}")
async def visit_workflow_open_link(
    session_id: int,
    link_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("execute_visits")),
):
    _ = current_user
    try:
        _session, url = visit_service.mark_link_opened(db, session_id, link_key)
    except visit_service.VisitWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(url, status_code=303)


@router.post("/visit-workflows/{session_id}/notes")
async def visit_workflow_notes(session_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    form = await request.form()
    try:
        session = visit_service.update_visit_notes(
            db,
            session_id,
            VisitSessionNotesInput(notes=str(form.get("notes") or "")),
        )
    except visit_service.VisitWorkflowError as exc:
        return _render_session_page(request, db=db, current_user=current_user, session_id=session_id, error_message=str(exc), status_code=400)
    return RedirectResponse(f"/visit-workflows/{session.id}", status_code=303)


@router.post("/visit-workflows/{session_id}/preview")
async def visit_workflow_preview(session_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    form = await request.form()
    upload = form.get("visit_file")
    if upload is None or not getattr(upload, "filename", ""):
        return _render_session_page(request, db=db, current_user=current_user, session_id=session_id, error_message="Upload a completed visit workbook before previewing", status_code=400)
    try:
        file_bytes = await upload.read()
        raw_payload = visit_service.visit_workbook_to_payload(file_bytes, uploaded_filename=upload.filename)
        preview = visit_service.preview_visit_workbook(
            db,
            session_id,
            raw_payload,
            persist=True,
            uploaded_filename=upload.filename,
        )
        session = preview.session
    except visit_service.VisitWorkflowError as exc:
        return _render_session_page(request, db=db, current_user=current_user, session_id=session_id, error_message=str(exc), status_code=400)
    return _render_session_page(
        request,
        db=db,
        current_user=current_user,
        session=session,
        preview=preview,
        raw_payload=raw_payload,
        uploaded_filename=upload.filename,
    )


@router.post("/visit-workflows/{session_id}/commit")
async def visit_workflow_commit(session_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    form = await request.form()
    raw_payload = str(form.get("raw_payload") or "")
    uploaded_filename = str(form.get("uploaded_filename") or "") or None
    try:
        result = visit_service.commit_visit_workbook(
            db,
            session_id,
            raw_payload,
            uploaded_filename=uploaded_filename,
            user=current_user,
        )
        session = result.session
    except visit_service.VisitWorkflowError as exc:
        return _render_session_page(
            request,
            db=db,
            current_user=current_user,
            session_id=session_id,
            error_message=str(exc),
            raw_payload=raw_payload,
            uploaded_filename=uploaded_filename,
            status_code=400,
        )
    return _render_session_page(
        request,
        db=db,
        current_user=current_user,
        session=session,
        result=result,
        raw_payload=raw_payload,
        uploaded_filename=uploaded_filename,
    )


@router.post("/visit-workflows/{session_id}/complete")
async def visit_workflow_complete(session_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    form = await request.form()
    try:
        session = visit_service.complete_visit_session(
            db,
            session_id,
            VisitSessionCompleteInput(completion_note=str(form.get("completion_note") or "")),
        )
    except visit_service.VisitWorkflowError as exc:
        return _render_session_page(request, db=db, current_user=current_user, session_id=session_id, error_message=str(exc), status_code=400)
    return RedirectResponse(f"/visit-workflows/{session.id}/summary", status_code=303)


@router.get("/visit-workflows/{session_id}/summary")
async def visit_workflow_summary(session_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("execute_visits"))):
    try:
        session = visit_service.mark_summary_reviewed(db, session_id)
    except visit_service.VisitWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        "visit_workflow_summary.html",
        {
            "request": request,
            "current_user": current_user,
            "session": session,
        },
    )


@router.get("/settings/studies/{study_id}/workflow")
async def study_workflow_settings(study_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("manage_vocabularies"))):
    return _render_workflow_settings_page(request, db, current_user=current_user, study_id=study_id)


@router.post("/settings/studies/{study_id}/workflow")
async def save_study_workflow_settings(study_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("manage_vocabularies"))):
    form = await request.form()
    quick_link_labels = form.getlist("quick_link_label")
    quick_link_urls = form.getlist("quick_link_url")
    quick_links = [
        StudyWorkflowQuickLinkInput(label=str(label or ""), url=str(url or ""))
        for label, url in zip(quick_link_labels, quick_link_urls)
    ]
    template_upload = form.get("visit_template_file")
    try:
        workflow = visit_service.save_workflow_config(
            db,
            study_id,
            StudyWorkflowConfigInput(
                label=str(form.get("label") or ""),
                description=str(form.get("description") or ""),
                is_active=form.get("is_active") == "on",
                quick_links=quick_links,
            ),
            template_filename=getattr(template_upload, "filename", None) or None,
            template_bytes=await template_upload.read() if getattr(template_upload, "filename", "") else None,
        )
    except visit_service.VisitWorkflowError as exc:
        return _render_workflow_settings_page(
            request,
            db,
            current_user=current_user,
            study_id=study_id,
            error_message=str(exc),
            initial_values={
                "label": str(form.get("label") or ""),
                "description": str(form.get("description") or ""),
                "is_active": form.get("is_active") == "on",
                "quick_links": [{"label": item.label, "url": item.url} for item in quick_links],
            },
            status_code=400,
        )
    return RedirectResponse(f"/settings/studies/{study_id}/workflow?saved=1", status_code=303)


def _render_index(
    request: Request,
    db: Session,
    *,
    current_user,
    error_message: str | None = None,
    initial_values: dict[str, str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "visit_workflows.html",
        {
            "request": request,
            "current_user": current_user,
            "workflows": visit_service.list_active_workflows(db),
            "recent_sessions": visit_service.list_recent_sessions(db, limit=8),
            "draft_sessions": visit_service.list_recent_draft_sessions(db, limit=8),
            "submitted_sessions": visit_service.list_recent_submitted_sessions(db, limit=8),
            "studies": admin_service.list_studies(db),
            "error_message": error_message,
            "initial_values": initial_values or {},
        },
        status_code=status_code,
    )


def _render_session_page(
    request: Request,
    *,
    db: Session,
    current_user,
    session_id: int | None = None,
    session=None,
    preview=None,
    result=None,
    raw_payload: str = "",
    uploaded_filename: str | None = None,
    error_message: str | None = None,
    status_code: int = 200,
):
    if session is None:
        lookup_session_id = session_id if session_id is not None else int(request.path_params["session_id"])
        session = visit_service.get_visit_session(db, lookup_session_id)
    return templates.TemplateResponse(
        "visit_workflow_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "session": session,
            "preview": preview,
            "result": result,
            "raw_payload": raw_payload,
            "uploaded_filename": uploaded_filename,
            "error_message": error_message,
        },
        status_code=status_code,
    )


def _render_workflow_settings_page(
    request: Request,
    db: Session,
    *,
    current_user,
    study_id: int,
    error_message: str | None = None,
    initial_values: dict | None = None,
    status_code: int = 200,
):
    study = next((item for item in admin_service.list_studies(db) if item.id == study_id), None)
    if study is None:
        raise HTTPException(status_code=404, detail="Study not found")
    workflow = visit_service.get_workflow_for_study(db, study_id)
    values = {
        "label": workflow.label,
        "description": workflow.description or "",
        "is_active": workflow.is_active,
        "quick_links": [link.model_dump() for link in workflow.quick_links] or [{"label": "", "url": ""}],
    }
    if initial_values:
        values.update(initial_values)
    return templates.TemplateResponse(
        "study_workflow_form.html",
        {
            "request": request,
            "current_user": current_user,
            "study": study,
            "workflow": workflow,
            "values": values,
            "error_message": error_message,
            "saved": request.query_params.get("saved") == "1",
        },
        status_code=status_code,
    )


def _parse_datetime(value: str) -> datetime:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError("Visit date is required")
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    raise ValueError("Visit date must use a valid date or datetime value")

