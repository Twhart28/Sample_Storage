from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AnalysisImportCommitInput, BatchModifyImportCommitInput
from app.services import analyses as analysis_service
from app.services import auth as auth_service
from app.services import batch_modify as batch_modify_service
from app.services import sample_actions as sample_actions_service
from app.web.dependencies import require_current_user, require_permission, templates

router = APIRouter()


@router.get("/sample-actions")
async def sample_actions_workspace(request: Request, db: Session = Depends(get_db)):
    current_user = require_current_user(request, db)
    return templates.TemplateResponse(
        "sample_actions.html",
        {
            "request": request,
            "current_user": current_user,
            "actions": sample_actions_service.available_actions(current_user),
            "bootstrap": {
                "sample_ids": _parse_sample_ids(request),
                "storage_key": sample_actions_service.SELECTION_STORAGE_KEY,
                "actions": sample_actions_service.available_actions(current_user),
            },
        },
    )


@router.get("/sample-actions/analyze")
@router.get("/analyses")
async def analyses_workspace(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("process_analysis")(request, db)
    return _render_analysis_page(
        request,
        current_user=current_user,
        sample_ids=_parse_sample_ids(request),
    )


@router.get("/analyses/new")
async def analyses_workspace_legacy(request: Request):
    query = request.url.query
    return RedirectResponse(f"/sample-actions/analyze?{query}" if query else "/sample-actions/analyze", status_code=303)


@router.get("/sample-actions/analyze/log")
@router.get("/analyses/log")
async def analysis_log_download(request: Request, db: Session = Depends(get_db)):
    _ = require_permission("process_analysis")(request, db)
    sample_ids = _parse_sample_ids(request)
    try:
        workbook = analysis_service.generate_analysis_log_xlsx(db, sample_ids)
    except analysis_service.AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="analysis-log.xlsx"'},
    )


@router.post("/sample-actions/analyze/preview")
@router.post("/analyses/preview")
async def analysis_preview(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("process_analysis")(request, db)
    form = await request.form()
    sample_ids = _parse_sample_ids(request)
    upload = form.get("analysis_file")
    raw_payload = str(form.get("raw_payload") or "")
    try:
        if upload is not None and getattr(upload, "filename", ""):
            file_bytes = await upload.read()
            raw_payload = analysis_service.analysis_workbook_to_payload(file_bytes)
        if not raw_payload:
            raise analysis_service.AnalysisError("Upload an analysis workbook before previewing")
        preview = analysis_service.preview_analysis_import(db, raw_payload)
    except analysis_service.AnalysisError as exc:
        return _render_analysis_page(
            request,
            current_user=current_user,
            sample_ids=sample_ids,
            error_message=str(exc),
            status_code=400,
        )

    return _render_analysis_page(
        request,
        current_user=current_user,
        sample_ids=sample_ids,
        raw_payload=raw_payload,
        preview=preview,
    )


@router.post("/sample-actions/analyze/commit")
@router.post("/analyses/commit")
async def analysis_commit(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("process_analysis")(request, db)
    form = await request.form()
    raw_payload = str(form.get("raw_payload") or "")
    sample_ids = _parse_sample_ids(request)
    try:
        result = analysis_service.commit_analysis_import(
            db,
            AnalysisImportCommitInput(raw_payload=raw_payload),
            current_user,
        )
    except analysis_service.AnalysisError as exc:
        return _render_analysis_page(
            request,
            current_user=current_user,
            sample_ids=sample_ids,
            error_message=str(exc),
            raw_payload=raw_payload,
            status_code=400,
        )
    except Exception as exc:
        return _render_analysis_page(
            request,
            current_user=current_user,
            sample_ids=sample_ids,
            error_message=f"Analysis commit failed: {exc}",
            raw_payload=raw_payload,
            status_code=500,
        )

    return _render_analysis_page(
        request,
        current_user=current_user,
        sample_ids=sample_ids,
        raw_payload=raw_payload,
        result=result,
    )


@router.get("/sample-actions/modify")
async def modify_workspace(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    return _render_modify_page(
        request,
        current_user=current_user,
        sample_ids=_parse_sample_ids(request),
    )


@router.get("/sample-actions/modify/log")
async def modify_log_download(request: Request, db: Session = Depends(get_db)):
    _ = require_permission("edit_samples")(request, db)
    sample_ids = _parse_sample_ids(request)
    try:
        workbook = batch_modify_service.generate_modify_log_xlsx(db, sample_ids)
    except batch_modify_service.BatchModifyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="batch-modify.xlsx"'},
    )


@router.post("/sample-actions/modify/preview")
async def modify_preview(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    form = await request.form()
    sample_ids = _parse_sample_ids(request)
    upload = form.get("modify_file")
    raw_payload = str(form.get("raw_payload") or "")
    try:
        if upload is not None and getattr(upload, "filename", ""):
            file_bytes = await upload.read()
            raw_payload = batch_modify_service.modify_workbook_to_payload(file_bytes)
        if not raw_payload:
            raise batch_modify_service.BatchModifyError("Upload a batch modify workbook before previewing")
        preview = batch_modify_service.preview_modify_import(db, raw_payload)
    except batch_modify_service.BatchModifyError as exc:
        return _render_modify_page(
            request,
            current_user=current_user,
            sample_ids=sample_ids,
            error_message=str(exc),
            status_code=400,
        )

    return _render_modify_page(
        request,
        current_user=current_user,
        sample_ids=sample_ids,
        raw_payload=raw_payload,
        preview=preview,
    )


@router.post("/sample-actions/modify/commit")
async def modify_commit(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    form = await request.form()
    raw_payload = str(form.get("raw_payload") or "")
    sample_ids = _parse_sample_ids(request)
    try:
        result = batch_modify_service.commit_modify_import(
            db,
            BatchModifyImportCommitInput(raw_payload=raw_payload),
            current_user,
        )
    except batch_modify_service.BatchModifyError as exc:
        return _render_modify_page(
            request,
            current_user=current_user,
            sample_ids=sample_ids,
            error_message=str(exc),
            raw_payload=raw_payload,
            status_code=400,
        )
    except Exception as exc:
        return _render_modify_page(
            request,
            current_user=current_user,
            sample_ids=sample_ids,
            error_message=f"Batch modify commit failed: {exc}",
            raw_payload=raw_payload,
            status_code=500,
        )

    return _render_modify_page(
        request,
        current_user=current_user,
        sample_ids=sample_ids,
        raw_payload=raw_payload,
        result=result,
    )


def _render_analysis_page(
    request: Request,
    *,
    current_user,
    sample_ids: list[int],
    error_message: str | None = None,
    raw_payload: str = "",
    preview=None,
    result=None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "sample_actions_analyze.html",
        {
            "request": request,
            "current_user": current_user,
            "error_message": error_message,
            "raw_payload": raw_payload,
            "preview": preview,
            "result": result,
            "bootstrap": {
                "sample_ids": sample_ids,
                "storage_key": sample_actions_service.SELECTION_STORAGE_KEY,
                "workspace_url": sample_actions_service.WORKSPACE_URL,
                "download_url": "/sample-actions/analyze/log",
            },
        },
        status_code=status_code,
    )


def _render_modify_page(
    request: Request,
    *,
    current_user,
    sample_ids: list[int],
    error_message: str | None = None,
    raw_payload: str = "",
    preview=None,
    result=None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "sample_actions_modify.html",
        {
            "request": request,
            "current_user": current_user,
            "error_message": error_message,
            "raw_payload": raw_payload,
            "preview": preview,
            "result": result,
            "bootstrap": {
                "sample_ids": sample_ids,
                "storage_key": sample_actions_service.SELECTION_STORAGE_KEY,
                "workspace_url": sample_actions_service.WORKSPACE_URL,
                "download_url": "/sample-actions/modify/log",
            },
        },
        status_code=status_code,
    )


def _parse_sample_ids(request: Request) -> list[int]:
    parsed: list[int] = []
    for value in request.query_params.getlist("sample_ids"):
        try:
            sample_id = int(value)
        except ValueError:
            continue
        if sample_id > 0 and sample_id not in parsed:
            parsed.append(sample_id)
    return parsed
