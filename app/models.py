from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StorageNodeType(str, Enum):
    freezer = "freezer"
    shelf = "shelf"
    rack = "rack"
    box = "box"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    events: Mapped[list[Event]] = relationship("Event", back_populates="user")


class SampleType(Base):
    __tablename__ = "sample_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    samples: Mapped[list[Sample]] = relationship("Sample", back_populates="sample_type")


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="active")
    volume: Mapped[Optional[float]] = mapped_column()
    volume_units: Mapped[Optional[str]] = mapped_column(String(20))
    sample_type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sample_types.id")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    sample_type: Mapped[Optional[SampleType]] = relationship(
        "SampleType", back_populates="samples"
    )
    location: Mapped[Optional[SampleLocation]] = relationship(
        "SampleLocation", back_populates="sample", uselist=False
    )
    events: Mapped[list[Event]] = relationship("Event", back_populates="sample")


class StorageNode(Base):
    __tablename__ = "storage_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[StorageNodeType] = mapped_column(SqlEnum(StorageNodeType))
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_nodes.id")
    )

    parent: Mapped[Optional[StorageNode]] = relationship(
        "StorageNode", remote_side=[id], back_populates="children"
    )
    children: Mapped[list[StorageNode]] = relationship(
        "StorageNode", back_populates="parent", cascade="all, delete"
    )
    positions: Mapped[list[StoragePosition]] = relationship(
        "StoragePosition", back_populates="box"
    )

    def path_names(self) -> list[str]:
        current = self
        names = []
        while current:
            names.append(current.name)
            current = current.parent
        return list(reversed(names))


class StoragePosition(Base):
    __tablename__ = "storage_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("storage_nodes.id"))
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(10), nullable=False)

    box: Mapped[StorageNode] = relationship("StorageNode", back_populates="positions")
    location: Mapped[Optional[SampleLocation]] = relationship(
        "SampleLocation", back_populates="position", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("box_id", "row", "col", name="uq_box_row_col"),
    )


class SampleLocation(Base):
    __tablename__ = "sample_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), unique=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("storage_positions.id"), unique=True
    )
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    sample: Mapped[Sample] = relationship("Sample", back_populates="location")
    position: Mapped[StoragePosition] = relationship(
        "StoragePosition", back_populates="location"
    )


class EventType(str, Enum):
    create_sample = "create_sample"
    update_sample = "update_sample"
    place_sample = "place_sample"
    move_sample = "move_sample"
    status_change = "status_change"
    create_storage = "create_storage"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[EventType] = mapped_column(SqlEnum(EventType))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    sample_id: Mapped[Optional[int]] = mapped_column(ForeignKey("samples.id"))
    from_position_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_positions.id")
    )
    to_position_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_positions.id")
    )
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    user: Mapped[Optional[User]] = relationship("User", back_populates="events")
    sample: Mapped[Optional[Sample]] = relationship("Sample", back_populates="events")

    @property
    def payload(self) -> dict:
        if not self.payload_json:
            return {}
        return json.loads(self.payload_json)

    def set_payload(self, payload: dict) -> None:
        self.payload_json = json.dumps(payload)
