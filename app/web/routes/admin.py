from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import SampleTypeCreate, StudyCreate
from app.services import admin as admin_service
from app.web.dependencies import require_permission, templates

router = APIRouter()


@router.get("/admin/configuration")
async def admin_configuration(current_user=Depends(require_permission("manage_vocabularies"))):
    _ = current_user
    return RedirectResponse("/settings", status_code=303)


@router.get("/settings/sample-types")
@router.get("/admin/configuration/sample-types")
async def sample_type_settings(request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("manage_vocabularies"))):
    return _render_sample_type_page(request, db, current_user=current_user)


@router.get("/settings/studies")
@router.get("/admin/configuration/studies")
async def study_settings(request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("manage_vocabularies"))):
    return _render_study_page(request, db, current_user=current_user)


@router.post("/admin/sample-types")
async def create_sample_type(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_vocabularies")),
):
    try:
        admin_service.create_sample_type(
            db,
            SampleTypeCreate(
                name=name.strip(),
                description=(description or "").strip() or None,
            ),
        )
    except admin_service.AdminError as exc:
        return _render_sample_type_page(request, db, current_user=current_user, error_message=str(exc), status_code=400)
    return RedirectResponse("/settings/sample-types", status_code=303)


@router.post("/admin/sample-types/{sample_type_id}")
async def update_sample_type(
    sample_type_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_vocabularies")),
):
    try:
        admin_service.update_sample_type(
            db,
            sample_type_id,
            SampleTypeCreate(
                name=name.strip(),
                description=(description or "").strip() or None,
            ),
        )
    except admin_service.AdminError as exc:
        return _render_sample_type_page(request, db, current_user=current_user, error_message=str(exc), status_code=400)
    return RedirectResponse("/settings/sample-types", status_code=303)


@router.post("/admin/sample-types/{sample_type_id}/delete")
async def delete_sample_type(
    sample_type_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_vocabularies")),
):
    try:
        admin_service.delete_sample_type(db, sample_type_id)
    except admin_service.AdminError as exc:
        return _render_sample_type_page(request, db, current_user=current_user, error_message=str(exc), status_code=400)
    return RedirectResponse("/settings/sample-types", status_code=303)


@router.post("/admin/studies")
async def create_study(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_vocabularies")),
):
    try:
        admin_service.create_study(
            db,
            StudyCreate(
                name=name.strip(),
                description=(description or "").strip() or None,
            ),
        )
    except admin_service.AdminError as exc:
        return _render_study_page(request, db, current_user=current_user, error_message=str(exc), status_code=400)
    return RedirectResponse("/settings/studies", status_code=303)


@router.post("/admin/studies/{study_id}")
async def update_study(
    study_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_vocabularies")),
):
    try:
        admin_service.update_study(
            db,
            study_id,
            StudyCreate(
                name=name.strip(),
                description=(description or "").strip() or None,
            ),
        )
    except admin_service.AdminError as exc:
        return _render_study_page(request, db, current_user=current_user, error_message=str(exc), status_code=400)
    return RedirectResponse("/settings/studies", status_code=303)


@router.post("/admin/studies/{study_id}/delete")
async def delete_study(
    study_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_vocabularies")),
):
    try:
        admin_service.delete_study(db, study_id)
    except admin_service.AdminError as exc:
        return _render_study_page(request, db, current_user=current_user, error_message=str(exc), status_code=400)
    return RedirectResponse("/settings/studies", status_code=303)


def _render_sample_type_page(
    request: Request,
    db: Session,
    *,
    current_user,
    error_message: str | None = None,
    status_code: int = 200,
):
    sample_types = admin_service.list_sample_types(db)
    usage_counts = {sample_type.id: admin_service.count_samples_for_sample_type(db, sample_type.id) for sample_type in sample_types}
    return templates.TemplateResponse(
        "admin_sample_types.html",
        {
            "request": request,
            "current_user": current_user,
            "sample_types": sample_types,
            "usage_counts": usage_counts,
            "error_message": error_message,
        },
        status_code=status_code,
    )


def _render_study_page(
    request: Request,
    db: Session,
    *,
    current_user,
    error_message: str | None = None,
    status_code: int = 200,
):
    studies = admin_service.list_studies(db)
    usage_counts = {study.id: admin_service.count_samples_for_study(db, study.id) for study in studies}
    return templates.TemplateResponse(
        "admin_studies.html",
        {
            "request": request,
            "current_user": current_user,
            "studies": studies,
            "usage_counts": usage_counts,
            "error_message": error_message,
        },
        status_code=status_code,
    )
