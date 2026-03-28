from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(str, Enum):
    admin = "admin"
    staff = "staff"


class StorageNodeType(str, Enum):
    freezer = "freezer"
    shelf = "shelf"
    rack = "rack"
    box = "box"


class StudyRole(str, Enum):
    current = "current"
    retired = "retired"


class EventType(str, Enum):
    create_sample = "create_sample"
    update_sample = "update_sample"
    analyze_sample = "analyze_sample"
    place_sample = "place_sample"
    move_sample = "move_sample"
    status_change = "status_change"
    add_note = "add_note"
    delete_sample = "delete_sample"
    create_storage = "create_storage"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), default=UserRole.staff)
    permissions_allow_json: Mapped[str | None] = mapped_column(Text)
    permissions_deny_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    events: Mapped[list[Event]] = relationship("Event", back_populates="user")
    sample_notes: Mapped[list[SampleNoteEntry]] = relationship("SampleNoteEntry", back_populates="user")
    analysis_batches: Mapped[list[AnalysisBatch]] = relationship("AnalysisBatch", back_populates="user")


class SampleType(Base):
    __tablename__ = "sample_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    samples: Mapped[list[Sample]] = relationship("Sample", back_populates="sample_type")


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    samples: Mapped[list[Sample]] = relationship("Sample", back_populates="study")

    @property
    def display_name(self) -> str:
        return self.name


class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = (
        Index(
            "ix_samples_identity_lookup",
            "sample_id",
            "sample_type_id",
            "visit_label",
            "timepoint_label",
            "aliquot_number",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    study_role: Mapped[StudyRole] = mapped_column(SqlEnum(StudyRole), default=StudyRole.current, index=True)
    is_archived: Mapped[bool] = mapped_column(default=False, index=True)
    is_out_for_analysis: Mapped[bool] = mapped_column(default=False, index=True)
    volume: Mapped[float | None] = mapped_column()
    volume_units: Mapped[str | None] = mapped_column(String(20), default="mL")
    sample_type_id: Mapped[int | None] = mapped_column(ForeignKey("sample_types.id"), index=True)
    study_id: Mapped[int | None] = mapped_column(ForeignKey("studies.id"), index=True)
    visit_label: Mapped[str | None] = mapped_column(String(30), index=True)
    timepoint_label: Mapped[str | None] = mapped_column(String(30), index=True)
    aliquot_number: Mapped[int | None] = mapped_column(Integer, index=True)
    thaw_count: Mapped[int] = mapped_column(Integer, default=0)
    hemolysis_classification: Mapped[int | None] = mapped_column(Integer, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    collection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )

    sample_type: Mapped[SampleType | None] = relationship("SampleType", back_populates="samples")
    study: Mapped[Study | None] = relationship("Study", back_populates="samples")
    location: Mapped[SampleLocation | None] = relationship(
        "SampleLocation", back_populates="sample", uselist=False, cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship("Event", back_populates="sample")
    note_entries: Mapped[list[SampleNoteEntry]] = relationship(
        "SampleNoteEntry", back_populates="sample", cascade="all, delete-orphan"
    )
    analysis_items: Mapped[list[AnalysisItem]] = relationship("AnalysisItem", back_populates="sample")


class StorageNode(Base):
    __tablename__ = "storage_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    node_type: Mapped[StorageNodeType] = mapped_column(SqlEnum(StorageNodeType))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("storage_nodes.id"))

    parent: Mapped[StorageNode | None] = relationship(
        "StorageNode", remote_side=[id], back_populates="children"
    )
    children: Mapped[list[StorageNode]] = relationship(
        "StorageNode", back_populates="parent", cascade="all, delete"
    )
    positions: Mapped[list[StoragePosition]] = relationship(
        "StoragePosition", back_populates="box", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        if self.nickname:
            return f"{self.name} ({self.nickname})"
        return self.name

    def path_names(self) -> list[str]:
        current: StorageNode | None = self
        names: list[str] = []
        while current:
            names.append(current.display_name)
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
    location: Mapped[SampleLocation | None] = relationship(
        "SampleLocation", back_populates="position", uselist=False
    )
    analysis_items_from: Mapped[list[AnalysisItem]] = relationship(
        "AnalysisItem",
        back_populates="from_position",
        foreign_keys="AnalysisItem.from_position_id",
    )
    analysis_items_to: Mapped[list[AnalysisItem]] = relationship(
        "AnalysisItem",
        back_populates="to_position",
        foreign_keys="AnalysisItem.to_position_id",
    )

    __table_args__ = (UniqueConstraint("box_id", "row", "col", name="uq_box_row_col"),)


class SampleLocation(Base):
    __tablename__ = "sample_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), unique=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("storage_positions.id"), unique=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    sample: Mapped[Sample] = relationship("Sample", back_populates="location")
    position: Mapped[StoragePosition] = relationship("StoragePosition", back_populates="location")


class SampleNoteEntry(Base):
    __tablename__ = "sample_note_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    sample: Mapped[Sample] = relationship("Sample", back_populates="note_entries")
    user: Mapped[User | None] = relationship("User", back_populates="sample_notes")


class AnalysisBatch(Base):
    __tablename__ = "analysis_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_type: Mapped[str | None] = mapped_column(String(100), index=True)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    overall_notes: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    user: Mapped[User | None] = relationship("User", back_populates="analysis_batches")
    items: Mapped[list[AnalysisItem]] = relationship(
        "AnalysisItem",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class AnalysisItem(Base):
    __tablename__ = "analysis_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("analysis_batches.id"), index=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), index=True)
    from_position_id: Mapped[int | None] = mapped_column(ForeignKey("storage_positions.id"))
    to_position_id: Mapped[int | None] = mapped_column(ForeignKey("storage_positions.id"))
    remaining_volume: Mapped[float | None] = mapped_column()
    volume_units: Mapped[str | None] = mapped_column(String(20), default="mL")
    thaw_increment: Mapped[int] = mapped_column(Integer, default=1)
    returned_to_storage: Mapped[bool] = mapped_column(default=True)
    sample_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    batch: Mapped[AnalysisBatch] = relationship("AnalysisBatch", back_populates="items")
    sample: Mapped[Sample] = relationship("Sample", back_populates="analysis_items")
    from_position: Mapped[StoragePosition | None] = relationship(
        "StoragePosition",
        back_populates="analysis_items_from",
        foreign_keys=[from_position_id],
    )
    to_position: Mapped[StoragePosition | None] = relationship(
        "StoragePosition",
        back_populates="analysis_items_to",
        foreign_keys=[to_position_id],
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[EventType] = mapped_column(SqlEnum(EventType))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"), index=True)
    from_position_id: Mapped[int | None] = mapped_column(ForeignKey("storage_positions.id"))
    to_position_id: Mapped[int | None] = mapped_column(ForeignKey("storage_positions.id"))
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    user: Mapped[User | None] = relationship("User", back_populates="events")
    sample: Mapped[Sample | None] = relationship("Sample", back_populates="events")
    from_position: Mapped[StoragePosition | None] = relationship("StoragePosition", foreign_keys=[from_position_id])
    to_position: Mapped[StoragePosition | None] = relationship("StoragePosition", foreign_keys=[to_position_id])

    @property
    def payload(self) -> dict[str, Any]:
        if not self.payload_json:
            return {}
        return json.loads(self.payload_json)

    def set_payload(self, payload: dict[str, Any]) -> None:
        self.payload_json = json.dumps(payload or {})
