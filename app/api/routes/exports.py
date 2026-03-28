from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ExportBundle, SampleSearchQuery
from app.services import events as event_service
from app.services import samples as sample_service
from app.web.dependencies import require_permission

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/snapshot")
async def export_snapshot(request: Request, db: Session = Depends(get_db)):
    _ = require_permission("export_data")(request, db)
    samples = sample_service.search_samples(db, SampleSearchQuery(sort="updated_at"))
    detailed = [sample_service.get_sample_detail(db, sample.id) for sample in samples]
    return ExportBundle(
        samples=[sample for sample in detailed if sample is not None],
        events=event_service.list_events(db, limit=250),
        exported_at=datetime.utcnow(),
    )
