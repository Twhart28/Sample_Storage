from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
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


class VisitSessionStatus(str, Enum):
    draft = "draft"
    completed = "completed"
    cancelled = "cancelled"


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
    visit_sessions: Mapped[list[VisitSession]] = relationship("VisitSession", back_populates="operator")


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
    workflow: Mapped[StudyWorkflow | None] = relationship(
        "StudyWorkflow",
        back_populates="study",
        uselist=False,
        cascade="all, delete-orphan",
    )
    visit_sessions: Mapped[list[VisitSession]] = relationship("VisitSession", back_populates="study")

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
    hemolysis_classification: Mapped[float | None] = mapped_column(index=True)
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
    __table_args__ = (UniqueConstraint("parent_id", "rack_slot_row", "rack_slot_col", name="uq_storage_sibling_rack_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    node_type: Mapped[StorageNodeType] = mapped_column(SqlEnum(StorageNodeType))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("storage_nodes.id"))
    rack_rows: Mapped[int | None] = mapped_column(Integer)
    rack_cols: Mapped[int | None] = mapped_column(Integer)
    rack_slot_row: Mapped[int | None] = mapped_column(Integer)
    rack_slot_col: Mapped[int | None] = mapped_column(Integer)

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
        return self.name

    def path_names(self) -> list[str]:
        current: StorageNode | None = self
        names: list[str] = []
        while current:
            names.append(current.display_name)
            current = current.parent
        return list(reversed(names))

    @property
    def rack_layout_label(self) -> str | None:
        if self.node_type != StorageNodeType.rack or self.rack_rows is None or self.rack_cols is None:
            return None
        return _rack_layout_label(self.rack_rows, self.rack_cols)

    @property
    def rack_slot_label(self) -> str | None:
        if self.node_type != StorageNodeType.box or self.rack_slot_row is None or self.rack_slot_col is None:
            return None
        return _rack_slot_label(self.rack_slot_row, self.rack_slot_col)


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


def _grid_label(row: int, col: int) -> str:
    return f"{_grid_column_label(col)}{row}"


def _grid_column_label(col: int) -> str:
    letters: list[str] = []
    current = col
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _rack_layout_label(rows: int, cols: int) -> str:
    return f"{rows} rows x {cols} cols"


def _rack_slot_label(row: int, col: int) -> str:
    return _grid_label(row, col)


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


class StudyWorkflow(Base):
    __tablename__ = "study_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sample_template_config_json: Mapped[str | None] = mapped_column(Text)
    quick_links_json: Mapped[str | None] = mapped_column(Text)
    summary_sections_json: Mapped[str | None] = mapped_column(Text)
    template_workbook_filename: Mapped[str | None] = mapped_column(String(255))
    template_workbook_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    is_active: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    study: Mapped[Study] = relationship("Study", back_populates="workflow")
    visit_sessions: Mapped[list[VisitSession]] = relationship("VisitSession", back_populates="workflow")

    @property
    def sample_template_config(self) -> dict[str, Any]:
        if not self.sample_template_config_json:
            return {}
        return json.loads(self.sample_template_config_json)

    def set_sample_template_config(self, payload: dict[str, Any]) -> None:
        self.sample_template_config_json = json.dumps(payload or {})

    @property
    def quick_links(self) -> list[dict[str, Any]]:
        if not self.quick_links_json:
            return []
        return json.loads(self.quick_links_json)

    def set_quick_links(self, payload: list[dict[str, Any]]) -> None:
        self.quick_links_json = json.dumps(payload or [])

    @property
    def summary_sections(self) -> list[dict[str, Any]]:
        if not self.summary_sections_json:
            return []
        return json.loads(self.summary_sections_json)

    def set_summary_sections(self, payload: list[dict[str, Any]]) -> None:
        self.summary_sections_json = json.dumps(payload or [])

    @property
    def has_template_workbook(self) -> bool:
        return bool(self.template_workbook_blob)


class VisitSession(Base):
    __tablename__ = "visit_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"), index=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("study_workflows.id"), index=True)
    participant_id: Mapped[str] = mapped_column(String(100), index=True)
    visit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    operator_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[VisitSessionStatus] = mapped_column(
        SqlEnum(VisitSessionStatus), default=VisitSessionStatus.draft, index=True
    )
    session_notes: Mapped[str | None] = mapped_column(Text)
    deviation_notes: Mapped[str | None] = mapped_column(Text)
    completion_note: Mapped[str | None] = mapped_column(Text)
    generated_workbook_filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_workbook_filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_workbook_payload_json: Mapped[str | None] = mapped_column(Text)
    step_status_json: Mapped[str | None] = mapped_column(Text)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )

    study: Mapped[Study] = relationship("Study", back_populates="visit_sessions")
    workflow: Mapped[StudyWorkflow] = relationship("StudyWorkflow", back_populates="visit_sessions")
    operator: Mapped[User | None] = relationship("User", back_populates="visit_sessions")
    samples: Mapped[list[VisitSessionSample]] = relationship(
        "VisitSessionSample",
        back_populates="visit_session",
        cascade="all, delete-orphan",
    )

    @property
    def uploaded_workbook_payload(self) -> dict[str, Any]:
        if not self.uploaded_workbook_payload_json:
            return {}
        return json.loads(self.uploaded_workbook_payload_json)

    def set_uploaded_workbook_payload(self, payload: dict[str, Any]) -> None:
        self.uploaded_workbook_payload_json = json.dumps(payload or {})

    @property
    def step_status(self) -> dict[str, Any]:
        if not self.step_status_json:
            return {}
        return json.loads(self.step_status_json)

    def set_step_status(self, payload: dict[str, Any]) -> None:
        self.step_status_json = json.dumps(payload or {})


class VisitSessionSample(Base):
    __tablename__ = "visit_session_samples"
    __table_args__ = (UniqueConstraint("visit_session_id", "sample_id", name="uq_visit_session_sample"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_session_id: Mapped[int] = mapped_column(ForeignKey("visit_sessions.id"), index=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    visit_session: Mapped[VisitSession] = relationship("VisitSession", back_populates="samples")
    sample: Mapped[Sample] = relationship("Sample")


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
