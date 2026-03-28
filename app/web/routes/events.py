from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import EventSearchQuery
from app.services import auth as auth_service
from app.services import events as event_service
from app.web.dependencies import require_current_user, templates

router = APIRouter()


@router.get("/events")
async def events_feed(
    request: Request,
    event_type: str | None = None,
    user_id: str | None = None,
    sample_query: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
):
    current_user = require_current_user(request, db)
    filters = EventSearchQuery(
        event_type=event_type or None,
        user_id=_parse_optional_int(user_id),
        sample_query=sample_query.strip(),
        date_from=_parse_filter_datetime(date_from),
        date_to=_parse_filter_datetime(date_to, end_of_minute=True),
        limit=150,
    )
    events = event_service.list_events(db, query=filters)
    return templates.TemplateResponse(
        "events.html",
        {
            "request": request,
            "current_user": current_user,
            "events": events,
            "events_json": [event.model_dump(mode="json") for event in events],
            "event_type_options": event_service.list_event_types(),
            "event_user_options": event_service.list_event_users(db),
            "filters": {
                "event_type": event_type or "",
                "user_id": user_id or "",
                "sample_query": sample_query,
                "date_from": date_from or "",
                "date_to": date_to or "",
            },
            "can_export_data": auth_service.has_permission(current_user, "export_data"),
        },
    )


def _parse_filter_datetime(value: str | None, *, end_of_minute: bool = False) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if end_of_minute and len(cleaned) == 16:
        return parsed.replace(second=59, microsecond=999999)
    return parsed


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None
