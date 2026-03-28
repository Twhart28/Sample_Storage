from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import auth as auth_service
from app.web.dependencies import templates

router = APIRouter()


@router.get("/login")
async def login_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "current_user": None,
            "is_first_user": auth_service.list_users(db) == [],
        },
    )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = auth_service.sync_user(db, username=username, full_name=full_name or None)
    request.session["username"] = user.username
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
