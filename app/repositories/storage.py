from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domain import models


NODE_OPTIONS = (
    joinedload(models.StorageNode.parent),
    selectinload(models.StorageNode.children),
    selectinload(models.StorageNode.positions)
    .joinedload(models.StoragePosition.location)
    .joinedload(models.SampleLocation.sample),
)


def list_root_nodes(db: Session) -> list[models.StorageNode]:
    stmt = (
        select(models.StorageNode)
        .where(models.StorageNode.parent_id.is_(None))
        .options(*NODE_OPTIONS)
        .order_by(models.StorageNode.name.asc())
    )
    return list(db.execute(stmt).unique().scalars().all())


def list_all_nodes(db: Session) -> list[models.StorageNode]:
    stmt = select(models.StorageNode).options(*NODE_OPTIONS).order_by(models.StorageNode.name.asc())
    return list(db.execute(stmt).unique().scalars().all())


def list_boxes(db: Session) -> list[models.StorageNode]:
    stmt = (
        select(models.StorageNode)
        .where(models.StorageNode.node_type == models.StorageNodeType.box)
        .options(joinedload(models.StorageNode.parent))
        .order_by(models.StorageNode.name.asc())
    )
    return list(db.execute(stmt).unique().scalars().all())


def get_node(db: Session, node_id: int) -> models.StorageNode | None:
    stmt = select(models.StorageNode).where(models.StorageNode.id == node_id).options(*NODE_OPTIONS)
    return db.execute(stmt).unique().scalar_one_or_none()


def get_position(db: Session, position_id: int) -> models.StoragePosition | None:
    stmt = (
        select(models.StoragePosition)
        .where(models.StoragePosition.id == position_id)
        .options(
            joinedload(models.StoragePosition.location).joinedload(models.SampleLocation.sample),
            joinedload(models.StoragePosition.box).joinedload(models.StorageNode.parent),
        )
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def occupancy_by_freezer(db: Session) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    stmt = (
        select(models.SampleLocation)
        .options(
            joinedload(models.SampleLocation.position)
            .joinedload(models.StoragePosition.box)
            .joinedload(models.StorageNode.parent)
        )
    )
    locations = db.execute(stmt).unique().scalars().all()
    for location in locations:
        node = location.position.box
        while node.parent is not None:
            if node.node_type == models.StorageNodeType.freezer:
                counts[node.display_name] += 1
                break
            node = node.parent
        else:
            if node.node_type == models.StorageNodeType.freezer:
                counts[node.display_name] += 1
    return counts
