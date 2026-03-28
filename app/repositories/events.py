from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.domain import models
from app.schemas import EventSearchQuery


def list_recent(db: Session, query: EventSearchQuery, sample_id: int | None = None) -> list[models.Event]:
    stmt = (
        select(models.Event)
        .options(
            joinedload(models.Event.sample),
            joinedload(models.Event.user),
            joinedload(models.Event.from_position).joinedload(models.StoragePosition.box),
            joinedload(models.Event.to_position).joinedload(models.StoragePosition.box),
        )
        .order_by(models.Event.created_at.desc())
        .limit(query.limit)
    )
    if sample_id is not None:
        stmt = stmt.where(models.Event.sample_id == sample_id)
    if not query.include_notes:
        stmt = stmt.where(models.Event.event_type != models.EventType.add_note)
    if query.event_type:
        try:
            event_type = models.EventType(query.event_type)
        except ValueError:
            return []
        stmt = stmt.where(models.Event.event_type == event_type)
    if query.user_id is not None:
        stmt = stmt.where(models.Event.user_id == query.user_id)
    if query.sample_query:
        sample_query = f"%{query.sample_query.strip()}%"
        stmt = stmt.outerjoin(models.Event.sample).where(
            or_(
                models.Sample.sample_id.ilike(sample_query),
                models.Event.payload_json.ilike(sample_query),
            )
        )
    if query.date_from is not None:
        stmt = stmt.where(models.Event.created_at >= query.date_from)
    if query.date_to is not None:
        stmt = stmt.where(models.Event.created_at <= query.date_to)
    return list(db.execute(stmt).unique().scalars().all())


def list_users_with_events(db: Session) -> list[models.User]:
    stmt = (
        select(models.User)
        .join(models.Event, models.Event.user_id == models.User.id)
        .group_by(models.User.id)
        .order_by(models.User.username.asc())
    )
    return list(db.execute(stmt).scalars().all())
