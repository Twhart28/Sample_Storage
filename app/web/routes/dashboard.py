from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import dashboard as dashboard_service
from app.web.dependencies import get_current_user, templates

router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    data = dashboard_service.build_dashboard(db)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "current_user": current_user, **data},
    )


@router.get("/")
async def root():
    return RedirectResponse("/dashboard")
