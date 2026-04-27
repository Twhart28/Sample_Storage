from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    BoxCreateInput,
    PlaceSampleInput,
    SampleSearchQuery,
    StorageNodeCreate,
)
from app.services import bulk_imports as bulk_import_service
from app.services import auth as auth_service
from app.services import samples as sample_service
from app.services import storage as storage_service
from app.web.dependencies import get_current_user, require_permission, templates

router = APIRouter()


@router.get("/storage")
async def storage_browser(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    search_query = str(request.query_params.get("q") or "").strip()
    return templates.TemplateResponse(
        "storage.html",
        {
            "request": request,
            "current_user": current_user,
            "root_nodes": storage_service.list_storage_tree(db),
            "search_query": search_query,
            "search_results": storage_service.search_boxes(db, search_query) if search_query else [],
        },
    )


@router.get("/storage/bulk")
async def bulk_storage_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("bulk_import_storage")),
):
    _ = (request, db, current_user)
    return RedirectResponse("/storage?bulk=boxes", status_code=303)


@router.get("/storage/bulk/template")
async def bulk_storage_template(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("bulk_import_storage")),
):
    _ = current_user
    all_nodes = storage_service.list_all_nodes(db)
    parent_paths = sorted(
        " > ".join(node.path_names())
        for node in all_nodes
        if node.node_type.value in {"shelf", "rack"}
    )
    return Response(
        content=bulk_import_service.box_template_xlsx(parent_paths=parent_paths),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="box-import-template.xlsx"'},
    )


@router.post("/storage/node")
async def create_storage_node(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_storage_tree")),
):
    form = await request.form()
    try:
        node = storage_service.create_storage_node(
            db,
            StorageNodeCreate(
                name=form.get("name", "").strip(),
                notes=form.get("notes") or None,
                node_type=form.get("node_type") or "freezer",
                parent_id=int(form.get("parent_id")) if form.get("parent_id") else None,
                rack_rows=int(form.get("rack_rows")) if form.get("rack_rows") else None,
                rack_cols=int(form.get("rack_cols")) if form.get("rack_cols") else None,
                rack_slot=(str(form.get("rack_slot")) or "").strip() or None,
            ),
            current_user,
        )
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/storage#node-{node.id}", status_code=303)


@router.post("/storage/box")
async def create_box(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_storage_tree")),
):
    form = await request.form()
    try:
        storage_service.create_box_positions(
            db,
            BoxCreateInput(
                box_id=int(form.get("box_id")),
                rows=int(form.get("rows")),
                cols=int(form.get("cols")),
            ),
            current_user,
        )
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/boxes/{int(form.get('box_id'))}", status_code=303)


@router.get("/boxes/{box_id}")
async def box_view(box_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    box = storage_service.get_box_view(db, box_id)
    if box is None:
        raise HTTPException(status_code=404, detail="Box not found")
    can_place_move = auth_service.has_permission(current_user, "place_move_samples")
    can_manage_storage = auth_service.has_permission(current_user, "manage_storage_tree")
    placeable_samples = []
    if can_place_move:
        placeable_samples = [
            sample
            for sample in sample_service.search_samples(db, SampleSearchQuery(location_state="unplaced"))
            if not sample.is_archived and not sample.is_out_for_analysis
        ]
    return templates.TemplateResponse(
        "box.html",
        {
            "request": request,
            "current_user": current_user,
            "box": box,
            "samples": placeable_samples,
            "can_place_move_samples": can_place_move,
            "can_manage_storage_tree": can_manage_storage,
            "column_headers": _build_box_columns(box),
            "grid_rows": _build_box_grid(box),
        },
    )


@router.post("/boxes/{box_id}/place")
async def place_from_box(
    box_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("place_move_samples")),
):
    form = await request.form()
    sample_service.place_sample(
        db,
        int(form.get("sample_id")),
        PlaceSampleInput(position_id=int(form.get("position_id"))),
        current_user,
    )
    return RedirectResponse(f"/boxes/{box_id}", status_code=303)


def _build_box_columns(box) -> list[str]:
    max_col = max((position.col for position in box.positions), default=0)
    return [chr(64 + col) for col in range(1, max_col + 1)]


def _build_box_grid(box) -> list[dict]:
    if not box.positions:
        return []
    positions_by_key = {(position.row, position.col): position for position in box.positions}
    max_row = max(position.row for position in box.positions)
    max_col = max(position.col for position in box.positions)
    grid_rows: list[dict] = []
    for row_number in range(1, max_row + 1):
        grid_rows.append(
            {
                "row_number": row_number,
                "cells": [positions_by_key.get((row_number, col_number)) for col_number in range(1, max_col + 1)],
            }
        )
    return grid_rows
