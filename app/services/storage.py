from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import models
from app.repositories import storage as storage_repository
from app.schemas import (
    BoxCreateInput,
    StorageLookupView,
    StorageNodeBatchMoveInput,
    StorageNodeCreate,
    StorageNodeMoveInput,
    StorageNodeUpdate,
    StorageNodeView,
    StoragePositionView,
)

ALLOWED_PARENTS: dict[str, set[str | None]] = {
    "freezer": {None},
    "shelf": {"freezer"},
    "rack": {"freezer", "shelf"},
    "box": {"shelf", "rack"},
}

CHILD_TYPES: dict[str | None, list[str]] = {
    None: ["freezer"],
    "freezer": ["shelf", "rack"],
    "shelf": ["rack", "box"],
    "rack": ["box"],
    "box": [],
}


class StorageError(Exception):
    pass


def list_storage_tree(db: Session) -> list[StorageNodeView]:
    return [_node_view(node) for node in storage_repository.list_root_nodes(db)]


def search_boxes(db: Session, query: str) -> list[StorageNodeView]:
    normalized = (query or "").strip().lower()
    if not normalized:
        return []
    matches: list[StorageNodeView] = []
    for node in storage_repository.list_boxes(db):
        haystack = " ".join(
            part
            for part in [
                node.name,
                node.display_name,
                _node_path(node),
                node.notes or "",
            ]
            if part
        ).lower()
        if normalized in haystack:
            matches.append(_node_view(node))
    return sorted(matches, key=lambda item: item.path.lower())


def list_boxes(db: Session) -> list[models.StorageNode]:
    return storage_repository.list_boxes(db)


def list_all_nodes(db: Session) -> list[models.StorageNode]:
    return storage_repository.list_all_nodes(db)


def get_position(db: Session, position_id: int) -> models.StoragePosition | None:
    return storage_repository.get_position(db, position_id)


def get_box_view(db: Session, box_id: int) -> StorageLookupView | None:
    box = storage_repository.get_node(db, box_id)
    if box is None or box.node_type != models.StorageNodeType.box:
        return None
    return StorageLookupView(
        box_id=box.id,
        box_name=box.display_name,
        box_path="/".join(box.path_names()),
        positions=[
            StoragePositionView(
                id=position.id,
                box_id=position.box_id,
                row=position.row,
                col=position.col,
                label=_position_label(position.row, position.col),
                occupied=position.location is not None,
                sample_id=position.location.sample_id if position.location else None,
                sample_identifier=position.location.sample.sample_id if position.location else None,
                sample_type_name=position.location.sample.sample_type.name if position.location and position.location.sample.sample_type else None,
                collection_at=position.location.sample.collection_at if position.location else None,
                visit_label=position.location.sample.visit_label if position.location else None,
                timepoint_label=position.location.sample.timepoint_label if position.location else None,
                aliquot_number=position.location.sample.aliquot_number if position.location else None,
            )
            for position in sorted(box.positions, key=lambda item: (item.row, item.col))
        ],
    )


def create_storage_node(
    db: Session,
    data: StorageNodeCreate,
    user: models.User | None,
    *,
    commit: bool = True,
) -> models.StorageNode:
    parent = _validate_parent(db, data.node_type, data.parent_id)
    name = data.name.strip()
    _ensure_unique_name(db, data.node_type, name)
    node = models.StorageNode(
        name=name,
        notes=_clean_optional_text(data.notes),
        node_type=models.StorageNodeType(data.node_type),
        parent_id=parent.id if parent else None,
    )
    db.add(node)
    db.flush()
    if node.node_type != models.StorageNodeType.box:
        _log_event(
            db,
            event_type=models.EventType.create_storage,
            user=user,
            payload={
                "action": "create",
                "node_id": node.id,
                "node_type": node.node_type.value,
                "name": node.name,
                "parent_id": node.parent_id,
                "path": _node_path(node),
            },
        )
    _finalize(db, node, commit)
    return node


def update_storage_node(
    db: Session,
    node_id: int,
    data: StorageNodeUpdate,
    user: models.User | None,
) -> models.StorageNode:
    node = storage_repository.get_node(db, node_id)
    if node is None:
        raise StorageError("Storage node not found")
    name = data.name.strip()
    _ensure_unique_name(db, node.node_type.value, name, exclude_node_id=node.id)
    before_snapshot = _storage_snapshot(node)
    node.name = name
    node.notes = _clean_optional_text(data.notes)
    db.add(node)
    db.flush()
    db.refresh(node)
    after_snapshot = _storage_snapshot(node)
    _log_event(
        db,
        event_type=models.EventType.create_storage,
        user=user,
        payload={
            "action": "update",
            "node_id": node.id,
            "node_type": node.node_type.value,
            "name": node.name,
            "path": _node_path(node),
            "before": before_snapshot,
            "after": after_snapshot,
            "changes": _storage_snapshot_changes(before_snapshot, after_snapshot),
        },
    )
    db.commit()
    db.refresh(node)
    return node


def move_storage_node(
    db: Session,
    node_id: int,
    data: StorageNodeMoveInput,
    user: models.User | None,
) -> models.StorageNode:
    node = storage_repository.get_node(db, node_id)
    if node is None:
        raise StorageError("Storage node not found")
    parent = _validate_parent(db, node.node_type.value, data.parent_id)
    if parent and _is_descendant(parent, node):
        raise StorageError("Cannot move a node inside its own subtree")
    before_path = _node_path(node)
    node.parent_id = parent.id if parent else None
    db.add(node)
    db.flush()
    db.refresh(node)
    _log_event(
        db,
        event_type=models.EventType.create_storage,
        user=user,
        payload={
            "action": "move",
            "node_id": node.id,
            "node_type": node.node_type.value,
            "name": node.name,
            "parent_id": node.parent_id,
            "before_path": before_path,
            "after_path": _node_path(node),
        },
    )
    db.commit()
    db.refresh(node)
    return node


def move_storage_nodes(
    db: Session,
    data: StorageNodeBatchMoveInput,
    user: models.User | None,
) -> list[models.StorageNode]:
    node_ids = _normalize_node_ids(data.node_ids)
    if not node_ids:
        raise StorageError("Select at least one storage node to move")
    nodes = _resolve_nodes_for_batch_move(db, node_ids)
    _validate_batch_selection(nodes)
    target_parent = _validate_batch_parent(db, nodes, data.parent_id)

    moved_nodes: list[models.StorageNode] = []
    before_paths = {node.id: _node_path(node) for node in nodes}
    batch_group_id = uuid4().hex
    destination_path = _node_path(target_parent) if target_parent else "Root"
    batch_group_title = f"Move to {destination_path}"
    for node in nodes:
        node.parent_id = target_parent.id if target_parent else None
        db.add(node)
        moved_nodes.append(node)

    db.flush()

    for node in moved_nodes:
        db.refresh(node)
        _log_event(
            db,
            event_type=models.EventType.create_storage,
            user=user,
            payload={
                "action": "move",
                "node_id": node.id,
                "node_type": node.node_type.value,
                "name": node.name,
                "parent_id": node.parent_id,
                "before_path": before_paths[node.id],
                "after_path": _node_path(node),
                "batch_group_kind": "storage_move_batch",
                "batch_group_id": batch_group_id,
                "batch_group_title": batch_group_title,
                "batch_action_label": "Move storage",
                "batch_workflow_label": "Storage move",
                "batch_sample_count": len(moved_nodes),
                "batch_count_label": "Items",
                "batch_destination_path": destination_path,
            },
        )

    db.commit()
    for node in moved_nodes:
        db.refresh(node)
    return moved_nodes


def delete_storage_node(db: Session, node_id: int, user: models.User | None) -> None:
    node = storage_repository.get_node(db, node_id)
    if node is None:
        raise StorageError("Storage node not found")
    if _has_occupied_positions(node):
        raise StorageError("Cannot delete a storage node that contains placed samples")
    payload = {
        "action": "delete",
        "node_id": node.id,
        "node_type": node.node_type.value,
        "name": node.name,
        "path": _node_path(node),
    }
    db.delete(node)
    _log_event(
        db,
        event_type=models.EventType.create_storage,
        user=user,
        payload=payload,
    )
    db.commit()


def create_box_positions(
    db: Session,
    data: BoxCreateInput,
    user: models.User | None,
    *,
    commit: bool = True,
) -> list[models.StoragePosition]:
    box = storage_repository.get_node(db, data.box_id)
    if box is None or box.node_type != models.StorageNodeType.box:
        raise StorageError("Box not found")
    if box.positions:
        raise StorageError("Box positions already exist")
    positions: list[models.StoragePosition] = []
    for row in range(1, data.rows + 1):
        for col in range(1, data.cols + 1):
            positions.append(
                models.StoragePosition(box_id=box.id, row=row, col=col, label=_position_label(row, col))
            )
    db.add_all(positions)
    db.flush()
    _log_event(
        db,
        event_type=models.EventType.create_storage,
        user=user,
        payload={
            "action": "create_box",
            "box_id": box.id,
            "node_id": box.id,
            "node_type": box.node_type.value,
            "name": box.name,
            "path": _node_path(box),
            "parent_path": "/".join(box.path_names()[:-1]) if len(box.path_names()) > 1 else None,
            "rows": data.rows,
            "cols": data.cols,
            "positions": len(positions),
        },
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return positions


def storage_path_for_position(position: models.StoragePosition) -> str:
    return "/".join(position.box.path_names() + [_position_label(position.row, position.col)])


def _validate_parent(
    db: Session,
    node_type: str,
    parent_id: int | None,
) -> models.StorageNode | None:
    parent = storage_repository.get_node(db, parent_id) if parent_id is not None else None
    if parent_id is not None and parent is None:
        raise StorageError("Parent node not found")
    parent_type = parent.node_type.value if parent else None
    if parent_type not in ALLOWED_PARENTS[node_type]:
        allowed = ", ".join(parent_type or "root" for parent_type in sorted(ALLOWED_PARENTS[node_type], key=lambda value: value or ""))
        raise StorageError(f"{node_type.title()} nodes can only be placed under: {allowed}")
    return parent


def _ensure_unique_name(
    db: Session,
    node_type: str,
    name: str,
    exclude_node_id: int | None = None,
) -> None:
    if node_type not in {"freezer", "box"}:
        return
    stmt = select(models.StorageNode).where(
        models.StorageNode.node_type == models.StorageNodeType(node_type),
        models.StorageNode.name == name,
    )
    if exclude_node_id is not None:
        stmt = stmt.where(models.StorageNode.id != exclude_node_id)
    duplicate = db.execute(stmt).scalar_one_or_none()
    if duplicate is not None:
        raise StorageError(f"{node_type.title()} names must be unique")


def _node_view(node: models.StorageNode) -> StorageNodeView:
    child_types = CHILD_TYPES[node.node_type.value]
    filled_positions = sum(1 for position in node.positions if position.location is not None)
    total_positions = len(node.positions)
    return StorageNodeView(
        id=node.id,
        name=node.name,
        notes=node.notes,
        display_name=node.display_name,
        path=_node_path(node),
        node_type=node.node_type.value,
        parent_id=node.parent_id,
        can_accept_children=bool(child_types),
        filled_positions=filled_positions,
        total_positions=total_positions,
        child_types=child_types,
        children=[_node_view(child) for child in sorted(node.children, key=_storage_sort_key)],
    )


def _is_descendant(candidate_parent: models.StorageNode, node: models.StorageNode) -> bool:
    current = candidate_parent
    while current is not None:
        if current.id == node.id:
            return True
        current = current.parent
    return False


def _validate_batch_parent(
    db: Session,
    nodes: list[models.StorageNode],
    parent_id: int | None,
) -> models.StorageNode | None:
    parent = storage_repository.get_node(db, parent_id) if parent_id is not None else None
    if parent_id is not None and parent is None:
        raise StorageError("Parent node not found")
    for node in nodes:
        allowed = ALLOWED_PARENTS[node.node_type.value]
        parent_type = parent.node_type.value if parent else None
        if parent_type not in allowed:
            raise StorageError(f"{node.node_type.value.title()} nodes can only be placed under: {', '.join(parent_type or 'root' for parent_type in sorted(allowed, key=lambda value: value or ''))}")
        if parent and _is_descendant(parent, node):
            raise StorageError("Cannot move a node inside its own subtree")
    return parent


def _validate_batch_selection(nodes: list[models.StorageNode]) -> None:
    selected_ids = {node.id for node in nodes}
    for node in nodes:
        current = node.parent
        while current is not None:
            if current.id in selected_ids:
                raise StorageError("Cannot move a parent and its descendant in the same batch")
            current = current.parent


def _resolve_nodes_for_batch_move(db: Session, node_ids: list[int]) -> list[models.StorageNode]:
    nodes: list[models.StorageNode] = []
    missing: list[int] = []
    for node_id in node_ids:
        node = storage_repository.get_node(db, node_id)
        if node is None:
            missing.append(node_id)
            continue
        nodes.append(node)
    if missing:
        raise StorageError("One or more selected storage nodes were not found")
    return nodes


def _normalize_node_ids(node_ids: list[int]) -> list[int]:
    normalized: list[int] = []
    for node_id in node_ids:
        if node_id not in normalized:
            normalized.append(node_id)
    return normalized


def _storage_sort_key(node: models.StorageNode) -> tuple[int, int, str]:
    type_order = {
        models.StorageNodeType.freezer: 0,
        models.StorageNodeType.shelf: 1,
        models.StorageNodeType.rack: 2,
        models.StorageNodeType.box: 3,
    }
    branch_rank = 0 if node.node_type != models.StorageNodeType.box else 1
    return (branch_rank, type_order.get(node.node_type, 9), node.name.lower())


def _has_occupied_positions(node: models.StorageNode) -> bool:
    if any(position.location is not None for position in node.positions):
        return True
    return any(_has_occupied_positions(child) for child in node.children)


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _node_path(node: models.StorageNode) -> str:
    return "/".join(node.path_names())


def _storage_snapshot(node: models.StorageNode) -> dict[str, str]:
    return {
        "name": node.name,
        "notes": node.notes or "--",
        "path": _node_path(node),
    }


def _storage_snapshot_changes(before: dict[str, str], after: dict[str, str]) -> list[dict[str, str]]:
    labels = {
        "name": "Name",
        "notes": "Notes",
        "path": "Path",
    }
    changes: list[dict[str, str]] = []
    for field, label in labels.items():
        before_value = before.get(field, "--")
        after_value = after.get(field, "--")
        if before_value != after_value:
            changes.append(
                {
                    "field": field,
                    "label": label,
                    "before": before_value,
                    "after": after_value,
                }
            )
    return changes


def _position_label(row: int, col: int) -> str:
    return f"{chr(64 + col)}{row}"


def _finalize(db: Session, entity, commit: bool) -> None:
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(entity)


def _log_event(
    db: Session,
    event_type: models.EventType,
    user: models.User | None,
    payload: dict,
) -> None:
    event = models.Event(event_type=event_type, user_id=user.id if user else None)
    event.set_payload(payload)
    db.add(event)
