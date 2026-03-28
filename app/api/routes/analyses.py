from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AnalysisBatchCreateInput, AnalysisPreviewRequest
from app.services import analyses as analysis_service
from app.web.dependencies import require_permission

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


@router.post("/preview")
async def preview_analysis_samples(
    payload: AnalysisPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _ = require_permission("process_analysis")(request, db)
    return analysis_service.preview_samples(db, payload)


@router.post("/")
async def submit_analysis_batch(
    payload: AnalysisBatchCreateInput,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user = require_permission("process_analysis")(request, db)
        return analysis_service.submit_analysis_batch(db, payload, user)
    except analysis_service.AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
