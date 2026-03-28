from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import EventSearchQuery
from app.services import events as event_service
from app.web.dependencies import require_current_user

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/")
async def list_events(
    request: Request,
    event_type: str | None = None,
    user_id: int | None = None,
    sample_query: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    _ = require_current_user(request, db)
    return event_service.list_events(
        db,
        query=EventSearchQuery(
            event_type=event_type or None,
            user_id=user_id,
            sample_query=sample_query.strip(),
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        ),
    )
