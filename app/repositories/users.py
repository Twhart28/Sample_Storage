from __future__ import annotations

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain import models


def get_by_username(db: Session, username: str) -> models.User | None:
    return db.execute(
        select(models.User).where(models.User.username == username)
    ).scalar_one_or_none()


def get_by_id(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def list_users(db: Session) -> list[models.User]:
    return list(db.execute(select(models.User).order_by(models.User.username.asc())).scalars())


def count_users(db: Session) -> int:
    return int(db.execute(select(func.count(models.User.id))).scalar_one())


def count_admin_users(db: Session) -> int:
    return int(
        db.execute(
            select(func.count(models.User.id)).where(models.User.role == models.UserRole.admin)
        ).scalar_one()
    )
