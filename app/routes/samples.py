from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.db import get_db
from app.routes.auth import get_current_user

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    sample_count = db.execute(select(models.Sample)).scalars().all()
    status_counts = defaultdict(int)
    for sample in sample_count:
        status_counts[sample.status] += 1

    freezer_counts = defaultdict(int)
    positions = (
        db.execute(select(models.SampleLocation).join(models.StoragePosition))
        .scalars()
        .all()
    )
    for location in positions:
        freezer = _freezer_for_position(location.position)
        freezer_counts[freezer] += 1

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "status_counts": status_counts,
            "freezer_counts": freezer_counts,
        },
    )


@router.get("/samples", response_model=None)
async def list_samples(
    request: Request,
    q: Optional[str] = None,
    status: Optional[str] = None,
    sample_type_id: Optional[int] = None,
    sort: str = "sample_id",
    db: Session = Depends(get_db),
):
    samples = crud.list_samples(db, q, status, sample_type_id, sort)
    sample_types = db.execute(select(models.SampleType)).scalars().all()
    if "application/json" in request.headers.get("accept", ""):
        return [schemas.SampleRead.model_validate(sample) for sample in samples]
    return templates.TemplateResponse(
        "samples_list.html",
        {
            "request": request,
            "samples": samples,
            "sample_types": sample_types,
            "filters": {
                "q": q or "",
                "status": status or "",
                "sample_type_id": sample_type_id,
                "sort": sort,
            },
        },
    )


@router.get("/samples/new")
async def new_sample(request: Request, db: Session = Depends(get_db)):
    sample_types = db.execute(select(models.SampleType)).scalars().all()
    return templates.TemplateResponse(
        "samples_form.html",
        {"request": request, "sample": None, "sample_types": sample_types},
    )


@router.post("/samples")
async def create_sample(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        data = schemas.SampleCreate(**payload).model_dump()
        sample = crud.create_sample(db, data, user)
        return schemas.SampleRead.model_validate(sample)
    form = await request.form()
    data = {
        "sample_id": form.get("sample_id"),
        "name": form.get("name"),
        "status": form.get("status", "active"),
        "volume": float(form.get("volume")) if form.get("volume") else None,
        "volume_units": form.get("volume_units"),
        "sample_type_id": int(form.get("sample_type_id")) if form.get("sample_type_id") else None,
        "notes": form.get("notes"),
    }
    sample = crud.create_sample(db, data, user)
    return RedirectResponse(f"/samples/{sample.id}", status_code=303)


@router.get("/samples/{sample_id}")
async def sample_detail(sample_id: int, request: Request, db: Session = Depends(get_db)):
    sample = db.get(models.Sample, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    location_path = None
    if sample.location:
        location_path = crud.storage_path_for_position(sample.location.position)
    if "application/json" in request.headers.get("accept", ""):
        return schemas.SampleRead.model_validate(sample)
    events = (
        db.execute(
            select(models.Event)
            .where(models.Event.sample_id == sample.id)
            .order_by(models.Event.created_at.desc())
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        "samples_detail.html",
        {
            "request": request,
            "sample": sample,
            "location_path": location_path,
            "events": events,
        },
    )


@router.get("/samples/{sample_id}/edit")
async def edit_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    sample = db.get(models.Sample, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    sample_types = db.execute(select(models.SampleType)).scalars().all()
    return templates.TemplateResponse(
        "samples_form.html",
        {"request": request, "sample": sample, "sample_types": sample_types},
    )


@router.post("/samples/{sample_id}")
async def update_sample(
    sample_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    sample = db.get(models.Sample, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    user = get_current_user(request, db)
    form = await request.form()
    data = {
        "name": form.get("name"),
        "status": form.get("status"),
        "volume": float(form.get("volume")) if form.get("volume") else None,
        "volume_units": form.get("volume_units"),
        "sample_type_id": int(form.get("sample_type_id")) if form.get("sample_type_id") else None,
        "notes": form.get("notes"),
    }
    crud.update_sample(db, sample, data, user)
    return RedirectResponse(f"/samples/{sample.id}", status_code=303)


@router.put("/samples/{sample_id}")
async def update_sample_api(
    sample_id: int,
    payload: schemas.SampleUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    sample = db.get(models.Sample, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    user = get_current_user(request, db)
    updated = crud.update_sample(db, sample, payload.model_dump(exclude_unset=True), user)
    return schemas.SampleRead.model_validate(updated)


@router.post("/samples/{sample_id}/place")
async def place_sample(
    sample_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    sample = db.get(models.Sample, sample_id)
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        position_id = payload.get("position_id")
    else:
        form = await request.form()
        position_id = form.get("position_id")
    position = db.get(models.StoragePosition, int(position_id) if position_id else None)
    if not sample or not position:
        raise HTTPException(status_code=404, detail="Sample or position not found")
    user = get_current_user(request, db)
    crud.place_or_move_sample(db, sample, position, user)
    if request.headers.get("content-type", "").startswith("application/json"):
        return JSONResponse({"status": "ok"})
    return RedirectResponse(f"/samples/{sample.id}", status_code=303)


@router.post("/samples/{sample_id}/move")
async def move_sample(
    sample_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    sample = db.get(models.Sample, sample_id)
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        to_position_id = payload.get("to_position_id")
    else:
        form = await request.form()
        to_position_id = form.get("to_position_id")
    position = db.get(models.StoragePosition, int(to_position_id) if to_position_id else None)
    if not sample or not position:
        raise HTTPException(status_code=404, detail="Sample or position not found")
    user = get_current_user(request, db)
    crud.move_sample(db, sample, position, user)
    if request.headers.get("content-type", "").startswith("application/json"):
        return JSONResponse({"status": "ok"})
    return RedirectResponse(f"/samples/{sample.id}", status_code=303)


def _freezer_for_position(position: models.StoragePosition) -> str:
    node = position.box
    while node.parent is not None:
        if node.node_type == models.StorageNodeType.freezer:
            return node.name
        node = node.parent
    if node.node_type == models.StorageNodeType.freezer:
        return node.name
    return "Unknown"
