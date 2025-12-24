from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/events")
async def events_feed(request: Request, db: Session = Depends(get_db)):
    events = crud.recent_events(db)
    if "application/json" in request.headers.get("accept", ""):
        return [
            {
                "id": event.id,
                "event_type": event.event_type.value,
                "sample_id": event.sample_id,
                "from_position_id": event.from_position_id,
                "to_position_id": event.to_position_id,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]
    return templates.TemplateResponse(
        "events.html", {"request": request, "events": events}
    )
