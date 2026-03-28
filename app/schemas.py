from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    username: str
    full_name: str | None = None
    role: Literal["admin", "staff"] = "staff"


class UserCreate(UserBase):
    pass


class UserRead(UserBase, OrmModel):
    id: int
    created_at: datetime


class SampleTypeBase(BaseModel):
    name: str
    description: str | None = None


class SampleTypeCreate(SampleTypeBase):
    pass


class SampleTypeRead(SampleTypeBase, OrmModel):
    id: int


class StudyBase(BaseModel):
    name: str
    description: str | None = None


class StudyCreate(StudyBase):
    pass


class StudyRead(StudyBase, OrmModel):
    id: int
    display_name: str


class SampleSearchQuery(BaseModel):
    q: str = ""
    sample_type_id: int | None = None
    sample_type_ids: list[int] = Field(default_factory=list)
    study_id: int | None = None
    study_ids: list[int] = Field(default_factory=list)
    study_role: Literal["current", "retired"] | None = None
    study_roles: list[Literal["current", "retired"]] = Field(default_factory=list)
    custody: Literal["in_storage", "unplaced", "out_for_analysis", "archived"] | None = None
    custodies: list[Literal["in_storage", "unplaced", "out_for_analysis", "archived"]] = Field(default_factory=list)
    usage: Literal["unused", "used"] | None = None
    usages: list[Literal["unused", "used"]] = Field(default_factory=list)
    location_state: Literal["placed", "unplaced"] | None = None
    storage_node_ids: list[int] = Field(default_factory=list)
    visit_label: str | None = None
    visit_labels: list[str] = Field(default_factory=list)
    timepoint_label: str | None = None
    timepoint_labels: list[str] = Field(default_factory=list)
    aliquot_number: int | None = None
    aliquot_min: int | None = None
    aliquot_max: int | None = None
    hemolysis_classification: int | None = None
    hemolysis_min: int | None = None
    hemolysis_max: int | None = None
    thaw_count_min: int | None = None
    thaw_count_max: int | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    collection_from: datetime | None = None
    collection_to: datetime | None = None
    registered_from: datetime | None = None
    registered_to: datetime | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
    has_notes: bool | None = None
    sort: Literal[
        "sample_id",
        "study",
        "sample_type",
        "study_role",
        "custody",
        "usage",
        "volume",
        "location",
        "visit_label",
        "timepoint_label",
        "aliquot_number",
        "hemolysis_classification",
        "thaw_count",
        "collection_at",
        "created_at",
        "updated_at",
    ] = "sample_id"
    sort_dir: Literal["asc", "desc"] = "asc"


class SampleCreateInput(BaseModel):
    sample_id: str
    sample_type_id: int | None = None
    study_id: int | None = None
    visit_label: str | None = None
    timepoint_label: str | None = None
    aliquot_number: int | None = None
    hemolysis_classification: int | None = None
    study_role: Literal["current", "retired"] = "current"
    volume: float | None = None
    volume_units: str | None = "mL"
    thaw_count: int = 0
    notes: str | None = None
    collection_at: datetime | None = None


class SampleUpdateInput(BaseModel):
    sample_type_id: int | None = None
    study_id: int | None = None
    visit_label: str | None = None
    timepoint_label: str | None = None
    aliquot_number: int | None = None
    hemolysis_classification: int | None = None
    study_role: Literal["current", "retired"] | None = None
    volume: float | None = None
    volume_units: str | None = None
    thaw_count: int | None = None
    notes: str | None = None
    collection_at: datetime | None = None


class PlaceSampleInput(BaseModel):
    position_id: int


class MoveSampleInput(BaseModel):
    to_position_id: int


class RetrieveSampleInput(BaseModel):
    note: str | None = None


class SampleNoteCreateInput(BaseModel):
    text: str


class SampleListItem(OrmModel):
    id: int
    sample_id: str
    study_role: str
    is_archived: bool = False
    is_out_for_analysis: bool = False
    custody_label: str
    usage_label: str
    volume: float | None = None
    volume_units: str | None = None
    thaw_count: int
    created_at: datetime
    updated_at: datetime
    collection_at: datetime | None = None
    sample_type_id: int | None = None
    sample_type_name: str | None = None
    study_id: int | None = None
    study_name: str | None = None
    visit_label: str | None = None
    timepoint_label: str | None = None
    aliquot_number: int | None = None
    hemolysis_classification: int | None = None
    location_label: str | None = None
    location_path: str | None = None
    location_position_id: int | None = None


class AnalysisPreviewRequest(BaseModel):
    sample_ids: list[int] = Field(default_factory=list)


class AnalysisPreviewSample(BaseModel):
    id: int
    sample_id: str
    study_role: str
    custody_label: str
    usage_label: str
    volume: float | None = None
    volume_units: str | None = None
    thaw_count: int
    sample_type_name: str | None = None
    study_name: str | None = None
    location_label: str | None = None
    location_path: str | None = None
    location_position_id: int | None = None
    eligible: bool = True
    ineligibility_reason: str | None = None


class AnalysisPreviewResponse(BaseModel):
    samples: list[AnalysisPreviewSample] = Field(default_factory=list)


class AnalysisBatchItemInput(BaseModel):
    sample_id: int
    remaining_volume: float | None = None
    returned_to_storage: bool = True
    return_position_id: int | None = None
    thaw_increment: int = 1
    sample_notes: str | None = None


class AnalysisBatchCreateInput(BaseModel):
    analysis_type: str | None = None
    performed_at: datetime | None = None
    overall_notes: str | None = None
    items: list[AnalysisBatchItemInput] = Field(default_factory=list)


class AnalysisBatchResult(BaseModel):
    id: int
    analysis_type: str | None = None
    performed_at: datetime | None = None
    overall_notes: str | None = None
    created_at: datetime
    returned_count: int = 0
    out_for_analysis_count: int = 0
    processed_count: int = 0
    sample_ids: list[int] = Field(default_factory=list)


class AnalysisImportRow(BaseModel):
    row_number: int
    sample_pk: str | None = None
    sample_id: str | None = None
    sample_type: str | None = None
    current_box: str | None = None
    current_position: str | None = None
    current_volume: str | None = None
    volume_units: str | None = None
    remaining_volume: str | None = None
    returned_to_storage: str | None = None
    return_box: str | None = None
    assigned_box_name: str | None = None
    return_position: str | None = None
    assigned_position: str | None = None
    thaw_increment: str | None = None
    sample_notes: str | None = None
    errors: list[str] = Field(default_factory=list)
    valid: bool = False
    status: Literal["valid", "invalid", "imported", "skipped", "failed"] = "invalid"


class AnalysisImportPreview(BaseModel):
    raw_payload: str
    analysis_type: str | None = None
    performed_at: str | None = None
    overall_notes: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[AnalysisImportRow] = Field(default_factory=list)
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    global_errors: list[str] = Field(default_factory=list)


class AnalysisImportCommitInput(BaseModel):
    raw_payload: str


class AnalysisImportCommitResult(BaseModel):
    rows: list[AnalysisImportRow] = Field(default_factory=list)
    imported_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    global_errors: list[str] = Field(default_factory=list)
    batch_id: int | None = None


class BatchModifyImportRow(BaseModel):
    row_number: int
    sample_pk: str | None = None
    sample_id: str | None = None
    current_sample_type: str | None = None
    current_study: str | None = None
    current_study_role: str | None = None
    current_visit: str | None = None
    current_timepoint: str | None = None
    current_aliquot: str | None = None
    current_hemolysis: str | None = None
    current_volume: str | None = None
    volume_units: str | None = None
    current_thaw_count: str | None = None
    current_notes: str | None = None
    current_collection_at: str | None = None
    sample_type: str | None = None
    study: str | None = None
    study_role: str | None = None
    visit: str | None = None
    timepoint: str | None = None
    aliquot: str | None = None
    hemolysis: str | None = None
    volume: str | None = None
    thaw_count: str | None = None
    notes: str | None = None
    collection_at: str | None = None
    errors: list[str] = Field(default_factory=list)
    valid: bool = False
    status: Literal["valid", "invalid", "imported", "skipped", "failed"] = "invalid"


class BatchModifyImportPreview(BaseModel):
    raw_payload: str
    headers: list[str] = Field(default_factory=list)
    rows: list[BatchModifyImportRow] = Field(default_factory=list)
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    global_errors: list[str] = Field(default_factory=list)


class BatchModifyImportCommitInput(BaseModel):
    raw_payload: str


class BatchModifyImportCommitResult(BaseModel):
    rows: list[BatchModifyImportRow] = Field(default_factory=list)
    imported_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    global_errors: list[str] = Field(default_factory=list)
    batch_group_id: str | None = None


class EventSearchQuery(BaseModel):
    event_type: str | None = None
    user_id: int | None = None
    sample_query: str = ""
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 100
    include_notes: bool = False


class EventContextItem(BaseModel):
    label: str
    value: str


class EventChangeItem(BaseModel):
    field: str
    label: str
    before: str
    after: str


class EventDetailSection(BaseModel):
    title: str
    layout: Literal["single_value", "compact", "full"] = "full"
    items: list[EventContextItem] = Field(default_factory=list)


class EventGroupItem(BaseModel):
    event_id: int
    sample_id: int | None = None
    sample_identifier: str | None = None
    title: str
    disposition: str | None = None
    volume_change: str | None = None
    thaw_increment: str | None = None
    location_outcome: str | None = None
    context_line: str | None = None
    related_url: str | None = None


class EventView(OrmModel):
    id: int
    event_type: str
    display_action: str
    sample_id: int | None = None
    sample_identifier: str | None = None
    user_id: int | None = None
    username: str | None = None
    from_position_id: int | None = None
    to_position_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    action_label: str
    summary: str
    title: str
    context_line: str | None = None
    drawer_context_line: str | None = None
    subtitle: str | None = None
    pill_items: list[EventContextItem] = Field(default_factory=list)
    primary_items: list[EventContextItem] = Field(default_factory=list)
    context_items: list[EventContextItem] = Field(default_factory=list)
    detail_items: list[EventContextItem] = Field(default_factory=list)
    change_items: list[EventChangeItem] = Field(default_factory=list)
    metadata_section: EventDetailSection | None = None
    detail_sections: list[EventDetailSection] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "low"
    is_high_risk: bool = False
    has_legacy_detail_gap: bool = False
    severity: Literal["neutral", "success", "warning", "danger"] = "neutral"
    related_url: str | None = None
    is_group_parent: bool = False
    is_group_child: bool = False
    group_kind: str | None = None
    group_id: str | None = None
    group_title: str | None = None
    group_count: int = 0
    group_expanded_default: bool = False
    group_children: list[EventGroupItem] = Field(default_factory=list)
    created_at: datetime


class SampleNoteEntryView(OrmModel):
    id: int
    sample_id: int
    user_id: int | None = None
    username: str | None = None
    text: str
    created_at: datetime


class SampleDetailView(OrmModel):
    id: int
    sample_id: str
    study_role: str
    is_archived: bool = False
    is_out_for_analysis: bool = False
    custody_label: str
    usage_label: str
    volume: float | None = None
    volume_units: str | None = None
    thaw_count: int
    notes: str | None = None
    sample_type_id: int | None = None
    sample_type_name: str | None = None
    study_id: int | None = None
    study_name: str | None = None
    visit_label: str | None = None
    timepoint_label: str | None = None
    aliquot_number: int | None = None
    hemolysis_classification: int | None = None
    collection_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    location_label: str | None = None
    location_path: str | None = None
    location_position_id: int | None = None
    note_entries: list[SampleNoteEntryView] = Field(default_factory=list)
    events: list[EventView] = Field(default_factory=list)


class SampleFilterOption(BaseModel):
    value: str
    label: str
    count: int
    selected: bool = False


class SampleFilterOptionsRequest(BaseModel):
    column: Literal["sample_type", "study", "study_role", "custody", "usage", "visit_label", "timepoint_label", "location"]
    filters: SampleSearchQuery = Field(default_factory=SampleSearchQuery)


class SampleFilterOptionsResponse(BaseModel):
    column: str
    options: list[SampleFilterOption] = Field(default_factory=list)


class StorageNodeCreate(BaseModel):
    name: str
    nickname: str | None = None
    notes: str | None = None
    node_type: Literal["freezer", "shelf", "rack", "box"]
    parent_id: int | None = None


class StorageNodeUpdate(BaseModel):
    name: str
    nickname: str | None = None
    notes: str | None = None


class StorageNodeMoveInput(BaseModel):
    parent_id: int | None = None


class BoxCreateInput(BaseModel):
    box_id: int
    rows: int
    cols: int


class StorageNodeView(OrmModel):
    id: int
    name: str
    nickname: str | None = None
    notes: str | None = None
    display_name: str
    node_type: str
    parent_id: int | None = None
    can_accept_children: bool
    child_types: list[str] = Field(default_factory=list)
    children: list["StorageNodeView"] = Field(default_factory=list)


class StoragePositionView(OrmModel):
    id: int
    box_id: int
    row: int
    col: int
    label: str
    occupied: bool
    sample_id: int | None = None
    sample_identifier: str | None = None
    sample_type_name: str | None = None
    collection_at: datetime | None = None
    visit_label: str | None = None
    timepoint_label: str | None = None
    aliquot_number: int | None = None


class StorageLookupView(OrmModel):
    box_id: int
    box_name: str
    box_path: str
    positions: list[StoragePositionView] = Field(default_factory=list)


class BulkSampleImportRow(BaseModel):
    row_number: int
    sample_id: str | None = None
    sample_type: str | None = None
    study: str | None = None
    visit: str | None = None
    timepoint: str | None = None
    aliquot: str | None = None
    hemolysis: str | None = None
    study_role: str | None = None
    volume: str | None = None
    volume_units: str | None = None
    thaw_count: str | None = None
    notes: str | None = None
    collection_at: str | None = None
    box: str | None = None
    assigned_box_name: str | None = None
    position: str | None = None
    assigned_position: str | None = None
    errors: list[str] = Field(default_factory=list)
    valid: bool = False
    status: Literal["valid", "invalid", "imported", "skipped", "failed"] = "invalid"


class BulkSampleImportPreview(BaseModel):
    raw_payload: str
    headers: list[str] = Field(default_factory=list)
    rows: list[BulkSampleImportRow] = Field(default_factory=list)
    target_box_id: int | None = None
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    global_errors: list[str] = Field(default_factory=list)


class BulkSampleImportCommitInput(BaseModel):
    raw_payload: str
    target_box_id: int | None = None


class BulkSampleImportCommitResult(BaseModel):
    rows: list[BulkSampleImportRow] = Field(default_factory=list)
    imported_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    target_box_id: int | None = None
    global_errors: list[str] = Field(default_factory=list)


class BulkBoxImportRow(BaseModel):
    row_number: int
    parent: str | None = None
    box: str | None = None
    rows: str | None = None
    cols: str | None = None
    box_nickname: str | None = None
    notes: str | None = None
    errors: list[str] = Field(default_factory=list)
    valid: bool = False
    status: Literal["valid", "invalid", "imported", "skipped", "failed"] = "invalid"


class BulkBoxImportPreview(BaseModel):
    raw_payload: str
    headers: list[str] = Field(default_factory=list)
    rows: list[BulkBoxImportRow] = Field(default_factory=list)
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    global_errors: list[str] = Field(default_factory=list)


class BulkBoxImportCommitInput(BaseModel):
    raw_payload: str


class BulkBoxImportCommitResult(BaseModel):
    rows: list[BulkBoxImportRow] = Field(default_factory=list)
    imported_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    global_errors: list[str] = Field(default_factory=list)


class ExportBundle(BaseModel):
    samples: list[SampleDetailView]
    events: list[EventView]
    exported_at: datetime


StorageNodeView.model_rebuild()
