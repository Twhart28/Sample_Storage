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
                node.rack_slot_label or "",
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
        rack_slot_row=box.rack_slot_row,
        rack_slot_col=box.rack_slot_col,
        rack_slot_col_label=models._grid_column_label(box.rack_slot_col) if box.rack_slot_col else None,
        rack_slot_label=box.rack_slot_label,
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
    rack_rows, rack_cols = _validated_rack_layout(data.node_type, data.rack_rows, data.rack_cols)
    rack_slot_row, rack_slot_col = _validated_rack_slot(
        db,
        node_type=data.node_type,
        parent=parent,
        rack_slot=data.rack_slot,
    )
    node = models.StorageNode(
        name=name,
        notes=_clean_optional_text(data.notes),
        node_type=models.StorageNodeType(data.node_type),
        parent_id=parent.id if parent else None,
        rack_rows=rack_rows,
        rack_cols=rack_cols,
        rack_slot_row=rack_slot_row,
        rack_slot_col=rack_slot_col,
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
                "rack_layout": node.rack_layout_label,
                "rack_slot": node.rack_slot_label,
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
    if node.node_type == models.StorageNodeType.rack:
        node.rack_rows, node.rack_cols = _validated_rack_layout(node.node_type.value, data.rack_rows, data.rack_cols)
        _ensure_rack_layout_can_fit_children(node)
    elif node.node_type == models.StorageNodeType.box:
        node.rack_slot_row, node.rack_slot_col = _validated_rack_slot(
            db,
            node_type=node.node_type.value,
            parent=node.parent,
            rack_slot=data.rack_slot,
            exclude_node_id=node.id,
        )
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
    before_slot = node.rack_slot_label
    before_parent_id = node.parent_id
    node.parent_id = parent.id if parent else None
    if node.node_type == models.StorageNodeType.box and node.parent_id != before_parent_id:
        node.rack_slot_row = None
        node.rack_slot_col = None
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
            "before_slot": before_slot,
            "after_slot": node.rack_slot_label,
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
    before_slots = {node.id: node.rack_slot_label for node in nodes}
    before_parent_ids = {node.id: node.parent_id for node in nodes}
    batch_group_id = uuid4().hex
    destination_path = _node_path(target_parent) if target_parent else "Root"
    batch_group_title = f"Move to {destination_path}"
    for node in nodes:
        node.parent_id = target_parent.id if target_parent else None
        if node.node_type == models.StorageNodeType.box and node.parent_id != before_parent_ids[node.id]:
            node.rack_slot_row = None
            node.rack_slot_col = None
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
                "before_slot": before_slots[node.id],
                "after_slot": node.rack_slot_label,
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
        rack_layout_rows=node.rack_rows,
        rack_layout_cols=node.rack_cols,
        rack_layout_label=node.rack_layout_label,
        rack_slot_row=node.rack_slot_row,
        rack_slot_col=node.rack_slot_col,
        rack_slot_col_label=models._grid_column_label(node.rack_slot_col) if node.rack_slot_col else None,
        rack_slot_label=node.rack_slot_label,
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
        "rack_layout": node.rack_layout_label or "--",
        "rack_slot": node.rack_slot_label or "--",
    }


def _storage_snapshot_changes(before: dict[str, str], after: dict[str, str]) -> list[dict[str, str]]:
    labels = {
        "name": "Name",
        "notes": "Notes",
        "path": "Path",
        "rack_layout": "Rack Layout",
        "rack_slot": "Rack Position",
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
    return models._grid_label(row, col)


def _validated_rack_layout(node_type: str, rack_rows: int | None, rack_cols: int | None) -> tuple[int | None, int | None]:
    if node_type != "rack":
        if rack_rows is not None or rack_cols is not None:
            raise StorageError("Only racks can have a rack layout")
        return (None, None)
    if rack_rows is None and rack_cols is None:
        return (None, None)
    if rack_rows is None or rack_cols is None:
        raise StorageError("Rack layout requires both rows and columns")
    if rack_rows <= 0 or rack_cols <= 0:
        raise StorageError("Rack layout rows and columns must be greater than zero")
    return (rack_rows, rack_cols)


def _validated_rack_slot(
    db: Session,
    *,
    node_type: str,
    parent: models.StorageNode | None,
    rack_slot: str | None,
    exclude_node_id: int | None = None,
) -> tuple[int | None, int | None]:
    normalized = _clean_optional_text(rack_slot)
    if node_type != "box":
        if normalized:
            raise StorageError("Only boxes can have a rack position")
        return (None, None)
    if not normalized:
        return (None, None)
    if parent is None or parent.node_type != models.StorageNodeType.rack:
        raise StorageError("Rack positions can only be used for boxes directly inside a rack")
    if parent.rack_rows is None or parent.rack_cols is None:
        raise StorageError("This rack does not have a layout configured")
    row, col = _parse_rack_slot_label(normalized)
    if row is None or col is None:
        raise StorageError("Rack position must use a label like A2 or C4")
    if row > parent.rack_rows or col > parent.rack_cols:
        raise StorageError(f"Rack position must fit inside the rack layout ({parent.rack_layout_label})")
    _ensure_unique_rack_slot(db, parent.id, row, col, exclude_node_id=exclude_node_id)
    return (row, col)


def _ensure_unique_rack_slot(
    db: Session,
    parent_id: int,
    row: int,
    col: int,
    *,
    exclude_node_id: int | None = None,
) -> None:
    stmt = select(models.StorageNode).where(
        models.StorageNode.parent_id == parent_id,
        models.StorageNode.rack_slot_row == row,
        models.StorageNode.rack_slot_col == col,
    )
    if exclude_node_id is not None:
        stmt = stmt.where(models.StorageNode.id != exclude_node_id)
    duplicate = db.execute(stmt).scalar_one_or_none()
    if duplicate is not None:
        raise StorageError(f"Rack position {models._rack_slot_label(row, col)} is already assigned in this rack")


def _ensure_rack_layout_can_fit_children(rack: models.StorageNode) -> None:
    if rack.node_type != models.StorageNodeType.rack:
        return
    if rack.rack_rows is None or rack.rack_cols is None:
        if any(child.rack_slot_row is not None or child.rack_slot_col is not None for child in rack.children):
            raise StorageError("Clear assigned box rack positions before removing the rack layout")
        return
    for child in rack.children:
        if child.rack_slot_row is None or child.rack_slot_col is None:
            continue
        if child.rack_slot_row > rack.rack_rows or child.rack_slot_col > rack.rack_cols:
            raise StorageError("Current box rack positions do not fit inside the updated rack layout")


def _parse_grid_label(value: str | None) -> tuple[int | None, int | None]:
    raw = (value or "").strip().upper()
    if not raw:
        return (None, None)
    letters: list[str] = []
    digits: list[str] = []
    for character in raw:
        if character.isalpha() and not digits:
            letters.append(character)
            continue
        if character.isdigit():
            digits.append(character)
            continue
        return (None, None)
    if not letters or not digits:
        return (None, None)
    col = 0
    for character in letters:
        col = (col * 26) + (ord(character) - 64)
    row = int("".join(digits))
    if row <= 0 or col <= 0:
        return (None, None)
    return (row, col)


def _parse_rack_slot_label(value: str | None) -> tuple[int | None, int | None]:
    raw = (value or "").strip().upper()
    if not raw:
        return (None, None)
    if raw.startswith("R") and "C" in raw[1:]:
        c_index = raw.find("C", 1)
        row_text = raw[1:c_index]
        col_text = raw[c_index + 1 :]
        if row_text.isdigit() and col_text.isdigit():
            row = int(row_text)
            col = int(col_text)
            if row > 0 and col > 0:
                return (row, col)
        return (None, None)
    return _parse_grid_label(raw)


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
