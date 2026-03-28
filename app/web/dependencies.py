from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories import users
from app.services import auth

DISPLAY_DATETIME_FORMAT = "%m/%d/%y %H:%M"
templates = Jinja2Templates(directory="app/templates")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "--"
    return value.strftime(DISPLAY_DATETIME_FORMAT)


templates.env.globals["format_datetime"] = format_datetime
templates.env.globals["has_permission"] = auth.has_permission


def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.session.get("username")
    if not username:
        return None
    return users.get_by_username(db, username)


def require_current_user(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=403, detail="Login required")
    return user


def require_admin_user(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    try:
        auth.require_admin(user)
    except auth.PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return user


def require_permission(permission: str):
    def dependency(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        try:
            auth.require_permission(user, permission)
        except auth.PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return user

    return dependency
