from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


class StorageError(Exception):
    pass


class SampleError(Exception):
    pass


def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.execute(
        select(models.User).where(models.User.username == username)
    ).scalar_one_or_none()


def create_user(db: Session, username: str, full_name: Optional[str]) -> models.User:
    user = models.User(username=username, full_name=full_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_sample_type(db: Session, name: str, description: Optional[str]) -> models.SampleType:
    sample_type = models.SampleType(name=name, description=description)
    db.add(sample_type)
    db.commit()
    db.refresh(sample_type)
    return sample_type


def list_samples(
    db: Session,
    query: Optional[str] = None,
    status: Optional[str] = None,
    sample_type_id: Optional[int] = None,
    sort: str = "sample_id",
) -> list[models.Sample]:
    stmt = select(models.Sample)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            models.Sample.sample_id.ilike(like)
            | models.Sample.name.ilike(like)
        )
    if status:
        stmt = stmt.where(models.Sample.status == status)
    if sample_type_id:
        stmt = stmt.where(models.Sample.sample_type_id == sample_type_id)
    if sort == "created_at":
        stmt = stmt.order_by(models.Sample.created_at.desc())
    else:
        stmt = stmt.order_by(models.Sample.sample_id.asc())
    return list(db.execute(stmt).scalars().all())


def create_sample(db: Session, data: dict, user: Optional[models.User]) -> models.Sample:
    sample = models.Sample(**data)
    db.add(sample)
    db.flush()
    _log_event(
        db,
        event_type=models.EventType.create_sample,
        user=user,
        sample=sample,
        payload={"sample_id": sample.sample_id},
    )
    db.commit()
    db.refresh(sample)
    return sample


def update_sample(db: Session, sample: models.Sample, data: dict, user: Optional[models.User]) -> models.Sample:
    previous_status = sample.status
    for key, value in data.items():
        if value is not None:
            setattr(sample, key, value)
    db.add(sample)
    _log_event(
        db,
        event_type=models.EventType.update_sample,
        user=user,
        sample=sample,
        payload={"updated_at": datetime.utcnow().isoformat()},
    )
    if "status" in data and data.get("status") and data.get("status") != previous_status:
        _log_event(
            db,
            event_type=models.EventType.status_change,
            user=user,
            sample=sample,
            payload={"from": previous_status, "to": data.get("status")},
        )
    db.commit()
    db.refresh(sample)
    return sample


def create_storage_node(
    db: Session,
    name: str,
    node_type: models.StorageNodeType,
    parent_id: Optional[int],
    user: Optional[models.User],
) -> models.StorageNode:
    node = models.StorageNode(name=name, node_type=node_type, parent_id=parent_id)
    db.add(node)
    db.flush()
    _log_event(
        db,
        event_type=models.EventType.create_storage,
        user=user,
        payload={"node_id": node.id, "node_type": node_type.value},
    )
    db.commit()
    db.refresh(node)
    return node


def create_box_positions(
    db: Session,
    box_id: int,
    rows: int,
    cols: int,
    user: Optional[models.User],
) -> list[models.StoragePosition]:
    positions = []
    for row in range(1, rows + 1):
        row_label = chr(64 + row)
        for col in range(1, cols + 1):
            label = f"{row_label}{col}"
            positions.append(
                models.StoragePosition(
                    box_id=box_id, row=row, col=col, label=label
                )
            )
    db.add_all(positions)
    _log_event(
        db,
        event_type=models.EventType.create_storage,
        user=user,
        payload={"box_id": box_id, "positions": len(positions)},
    )
    db.commit()
    return positions


def place_or_move_sample(
    db: Session,
    sample: models.Sample,
    position: models.StoragePosition,
    user: Optional[models.User],
) -> models.SampleLocation:
    if position.location:
        raise StorageError("Position already occupied")
    existing_location = sample.location
    if existing_location:
        from_position_id = existing_location.position_id
        existing_location.position_id = position.id
        existing_location.placed_at = datetime.utcnow()
        event_type = models.EventType.move_sample
    else:
        existing_location = models.SampleLocation(sample_id=sample.id, position_id=position.id)
        db.add(existing_location)
        from_position_id = None
        event_type = models.EventType.place_sample
    _log_event(
        db,
        event_type=event_type,
        user=user,
        sample=sample,
        from_position_id=from_position_id,
        to_position_id=position.id,
        payload={"position_id": position.id},
    )
    db.commit()
    db.refresh(existing_location)
    return existing_location


def move_sample(
    db: Session,
    sample: models.Sample,
    to_position: models.StoragePosition,
    user: Optional[models.User],
) -> models.SampleLocation:
    if to_position.location:
        raise StorageError("Destination position already occupied")
    if not sample.location:
        raise SampleError("Sample has no current location")
    from_position_id = sample.location.position_id
    sample.location.position_id = to_position.id
    sample.location.placed_at = datetime.utcnow()
    _log_event(
        db,
        event_type=models.EventType.move_sample,
        user=user,
        sample=sample,
        from_position_id=from_position_id,
        to_position_id=to_position.id,
        payload={"from": from_position_id, "to": to_position.id},
    )
    db.commit()
    db.refresh(sample.location)
    return sample.location


def storage_path_for_position(position: models.StoragePosition) -> str:
    node = position.box
    names = node.path_names()
    return "/".join(names + [position.label])


def storage_tree(db: Session) -> list[models.StorageNode]:
    return list(
        db.execute(
            select(models.StorageNode).where(models.StorageNode.parent_id.is_(None))
        ).scalars()
    )


def recent_events(db: Session, limit: int = 50) -> list[models.Event]:
    return list(
        db.execute(
            select(models.Event).order_by(models.Event.created_at.desc()).limit(limit)
        ).scalars()
    )


def seed_storage(db: Session, user: Optional[models.User]) -> None:
    freezer = create_storage_node(
        db, "Freezer A", models.StorageNodeType.freezer, None, user
    )
    shelf = create_storage_node(
        db, "Shelf 1", models.StorageNodeType.shelf, freezer.id, user
    )
    rack = create_storage_node(
        db, "Rack 1", models.StorageNodeType.rack, shelf.id, user
    )
    box = create_storage_node(
        db, "Box 1", models.StorageNodeType.box, rack.id, user
    )
    create_box_positions(db, box.id, rows=8, cols=12, user=user)


def _log_event(
    db: Session,
    event_type: models.EventType,
    user: Optional[models.User] = None,
    sample: Optional[models.Sample] = None,
    from_position_id: Optional[int] = None,
    to_position_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> models.Event:
    event = models.Event(
        event_type=event_type,
        user_id=user.id if user else None,
        sample_id=sample.id if sample else None,
        from_position_id=from_position_id,
        to_position_id=to_position_id,
        created_at=datetime.utcnow(),
    )
    if payload:
        event.set_payload(payload)
    db.add(event)
    db.flush()
    return event
