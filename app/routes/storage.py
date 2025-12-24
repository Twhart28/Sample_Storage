from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models
from app.db import get_db
from app.routes.auth import get_current_user

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/storage")
async def storage_browser(request: Request, db: Session = Depends(get_db)):
    root_nodes = crud.storage_tree(db)
    if "application/json" in request.headers.get("accept", ""):
        return [
            {
                "id": node.id,
                "name": node.name,
                "node_type": node.node_type.value,
                "children": [
                    {
                        "id": child.id,
                        "name": child.name,
                        "node_type": child.node_type.value,
                    }
                    for child in node.children
                ],
            }
            for node in root_nodes
        ]
    return templates.TemplateResponse(
        "storage.html", {"request": request, "root_nodes": root_nodes}
    )


@router.post("/storage/node")
async def create_storage_node(
    request: Request,
    db: Session = Depends(get_db),
):
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        name = payload.get("name")
        node_type = payload.get("node_type")
        parent_id = payload.get("parent_id")
    else:
        form = await request.form()
        name = form.get("name")
        node_type = form.get("node_type")
        parent_id = form.get("parent_id")
    parent_id = int(parent_id) if parent_id else None
    user = get_current_user(request, db)
    node = crud.create_storage_node(
        db,
        name=name,
        node_type=models.StorageNodeType(node_type),
        parent_id=parent_id,
        user=user,
    )
    if request.headers.get("content-type", "").startswith("application/json"):
        return JSONResponse({"id": node.id})
    return RedirectResponse(f"/storage#node-{node.id}", status_code=303)


@router.post("/storage/box")
async def create_box(
    request: Request,
    db: Session = Depends(get_db),
):
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        box_id = payload.get("box_id")
        rows = payload.get("rows")
        cols = payload.get("cols")
    else:
        form = await request.form()
        box_id = form.get("box_id")
        rows = form.get("rows")
        cols = form.get("cols")
    box_id = int(box_id)
    rows = int(rows)
    cols = int(cols)
    user = get_current_user(request, db)
    crud.create_box_positions(db, box_id, rows, cols, user)
    if request.headers.get("content-type", "").startswith("application/json"):
        return JSONResponse({"status": "ok"})
    return RedirectResponse(f"/boxes/{box_id}", status_code=303)


@router.get("/boxes/{box_id}")
async def box_view(
    box_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    box = db.get(models.StorageNode, box_id)
    if not box or box.node_type != models.StorageNodeType.box:
        raise HTTPException(status_code=404, detail="Box not found")
    positions = (
        db.execute(
            select(models.StoragePosition)
            .where(models.StoragePosition.box_id == box_id)
            .order_by(models.StoragePosition.row, models.StoragePosition.col)
        )
        .scalars()
        .all()
    )
    samples = db.execute(select(models.Sample)).scalars().all()
    if "application/json" in request.headers.get("accept", ""):
        return [
            {
                "id": position.id,
                "label": position.label,
                "row": position.row,
                "col": position.col,
                "occupied": position.location is not None,
                "sample_id": position.location.sample_id if position.location else None,
            }
            for position in positions
        ]
    return templates.TemplateResponse(
        "box.html",
        {
            "request": request,
            "box": box,
            "positions": positions,
            "samples": samples,
        },
    )


@router.post("/boxes/{box_id}/place")
async def place_from_box(
    box_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        sample_id = payload.get("sample_id")
        position_id = payload.get("position_id")
    else:
        form = await request.form()
        sample_id = form.get("sample_id")
        position_id = form.get("position_id")
    sample = db.get(models.Sample, int(sample_id) if sample_id else None)
    position = db.get(models.StoragePosition, int(position_id) if position_id else None)
    if not sample or not position:
        raise HTTPException(status_code=404, detail="Sample or position not found")
    user = get_current_user(request, db)
    crud.place_or_move_sample(db, sample, position, user)
    if request.headers.get("content-type", "").startswith("application/json"):
        return JSONResponse({"status": "ok"})
    return RedirectResponse(f"/boxes/{box_id}", status_code=303)
