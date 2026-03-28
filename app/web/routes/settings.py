from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import admin as admin_service
from app.services import auth as auth_service
from app.web.dependencies import require_current_user, require_permission, templates
from app.web.routes.samples import DEFAULT_VISIBLE_COLUMNS, TABLE_COLUMNS

BOX_FIELD_OPTIONS = [
    {"key": "type", "label": "Type", "default": True},
    {"key": "collection", "label": "Collection", "default": True},
    {"key": "visit", "label": "Visit", "default": True},
    {"key": "timepoint", "label": "Timepoint", "default": True},
    {"key": "aliquot", "label": "Aliquot", "default": True},
]
DEFAULT_BOX_ZOOM = 100

router = APIRouter()


@router.get("/settings")
async def settings_home(request: Request, db: Session = Depends(get_db), current_user=Depends(require_current_user)):
    return _render_settings_page(request, db, current_user=current_user)


@router.post("/settings/account")
async def update_account_settings(
    request: Request,
    full_name: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(require_current_user),
):
    auth_service.update_profile(db, current_user, full_name=(full_name or "").strip() or None)
    return RedirectResponse("/settings?saved=account", status_code=303)


@router.get("/settings/users")
async def user_settings(request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("manage_users"))):
    return _render_user_settings_page(request, db, current_user=current_user)


@router.post("/settings/users/{user_id}")
async def update_user_settings(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_users")),
):
    form = await request.form()
    try:
        auth_service.update_user_admin(
            db,
            current_user,
            user_id,
            full_name=(str(form.get("full_name") or "")).strip() or None,
            role=str(form.get("role") or "staff"),
            permissions=form.getlist("permissions"),
        )
    except auth_service.UserManagementError as exc:
        return _render_user_settings_page(request, db, current_user=current_user, error_message=str(exc), status_code=400)
    return RedirectResponse("/settings/users", status_code=303)


def _render_settings_page(request: Request, db: Session, *, current_user):
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "current_user": current_user,
            "saved_section": request.query_params.get("saved", ""),
            "settings_bootstrap": {
                "sample_columns": TABLE_COLUMNS,
                "default_sample_columns": DEFAULT_VISIBLE_COLUMNS,
                "box_fields": BOX_FIELD_OPTIONS,
                "default_box_zoom": DEFAULT_BOX_ZOOM,
            },
            "admin_links": _admin_links(db, current_user),
        },
    )


def _render_user_settings_page(
    request: Request,
    db: Session,
    *,
    current_user,
    error_message: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "settings_users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": auth_service.list_users(db),
            "permission_definitions": auth_service.list_permission_definitions(),
            "effective_permissions_by_user": {
                user.id: sorted(auth_service.effective_permissions(user)) for user in auth_service.list_users(db)
            },
            "error_message": error_message,
        },
        status_code=status_code,
    )


def _admin_links(db: Session, current_user) -> list[dict[str, object]]:
    links: list[dict[str, object]] = []
    if auth_service.has_permission(current_user, "manage_users"):
        links.append(
            {
                "title": "Users & Roles",
                "description": "Review users, update display names, and manage staff versus admin access.",
                "count": len(auth_service.list_users(db)),
                "href": "/settings/users",
            }
        )
    if auth_service.has_permission(current_user, "manage_vocabularies"):
        links.extend(
            [
                {
                    "title": "Sample Types",
                    "description": "Manage the controlled list used in sample forms, filters, and imports.",
                    "count": len(admin_service.list_sample_types(db)),
                    "href": "/settings/sample-types",
                },
                {
                    "title": "Studies",
                    "description": "Manage the controlled study list used in sample registration, search, and imports.",
                    "count": len(admin_service.list_studies(db)),
                    "href": "/settings/studies",
                },
            ]
        )
    return links
