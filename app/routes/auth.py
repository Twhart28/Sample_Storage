from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models
from app.db import get_db

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request, db: Session) -> None | models.User:
    username = request.session.get("username")
    if not username:
        return None
    return crud.get_user_by_username(db, username)


@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(request: Request, username: str = Form(...), db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, username)
    if not user:
        user = crud.create_user(db, username=username, full_name=None)
    request.session["username"] = user.username
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.post("/admin/seed")
async def seed(request: Request, db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, "admin")
    if not user:
        user = crud.create_user(db, username="admin", full_name="Admin")
    crud.seed_storage(db, user)
    return RedirectResponse("/storage", status_code=303)
