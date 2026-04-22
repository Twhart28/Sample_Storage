from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    BoxCreateInput,
    BulkBoxImportCommitInput,
    StorageNodeBatchMoveInput,
    StorageNodeCreate,
    StorageNodeMoveInput,
    StorageNodeUpdate,
)
from app.services import bulk_imports as bulk_import_service
from app.services import storage as storage_service
from app.web.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/api", tags=["storage"])


@router.get("/storage")
async def storage_browser(request: Request, db: Session = Depends(get_db)):
    _ = get_current_user(request, db)
    return storage_service.list_storage_tree(db)


@router.post("/storage/node")
async def create_storage_node(
    payload: StorageNodeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_storage_tree")),
):
    try:
        node = storage_service.create_storage_node(db, payload, current_user)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": node.id,
        "name": node.name,
        "notes": node.notes,
        "display_name": node.display_name,
        "node_type": node.node_type.value,
        "parent_id": node.parent_id,
    }


@router.patch("/storage/node/{node_id}")
async def update_storage_node(
    node_id: int,
    payload: StorageNodeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_storage_tree")),
):
    try:
        node = storage_service.update_storage_node(db, node_id, payload, current_user)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": node.id,
        "name": node.name,
        "notes": node.notes,
        "display_name": node.display_name,
        "node_type": node.node_type.value,
        "parent_id": node.parent_id,
    }


@router.post("/storage/node/{node_id}/move")
async def move_storage_node(
    node_id: int,
    payload: StorageNodeMoveInput,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_storage_tree")),
):
    try:
        node = storage_service.move_storage_node(db, node_id, payload, current_user)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "node_id": node.id, "parent_id": node.parent_id}


@router.post("/storage/nodes/move")
async def move_storage_nodes(
    payload: StorageNodeBatchMoveInput,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_storage_tree")),
):
    try:
        nodes = storage_service.move_storage_nodes(db, payload, current_user)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "moved_count": len(nodes),
        "node_ids": [node.id for node in nodes],
        "parent_id": payload.parent_id,
    }


@router.delete("/storage/node/{node_id}")
async def delete_storage_node(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manage_storage_tree")),
):
    try:
        storage_service.delete_storage_node(db, node_id, current_user)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/storage/box")
async def create_box(payload: BoxCreateInput, request: Request, db: Session = Depends(get_db), current_user=Depends(require_permission("manage_storage_tree"))):
    try:
        storage_service.create_box_positions(db, payload, current_user)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/storage/bulk/preview")
async def preview_storage_bulk(
    payload: BulkBoxImportCommitInput,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("bulk_import_storage")),
):
    _ = (request, current_user)
    return bulk_import_service.preview_box_import(db, payload.raw_payload)


@router.post("/storage/bulk/commit")
async def commit_storage_bulk(
    payload: BulkBoxImportCommitInput,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("bulk_import_storage")),
):
    _ = request
    return bulk_import_service.commit_box_import(db, payload, current_user)


@router.get("/boxes/{box_id}")
async def box_view(box_id: int, request: Request, db: Session = Depends(get_db)):
    _ = get_current_user(request, db)
    box = storage_service.get_box_view(db, box_id)
    if box is None:
        raise HTTPException(status_code=404, detail="Box not found")
    return box
