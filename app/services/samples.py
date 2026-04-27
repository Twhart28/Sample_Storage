from __future__ import annotations

from datetime import datetime
import math
import re

from sqlalchemy.orm import Session

from app.domain import models
from app.repositories import samples as sample_repository
from app.schemas import (
    EventView,
    MoveSampleInput,
    PlaceSampleInput,
    RetrieveSampleInput,
    SampleCreateInput,
    SampleDetailView,
    SampleFilterOption,
    SampleFilterOptionsResponse,
    SampleListItem,
    SampleNoteCreateInput,
    SampleNoteEntryView,
    SampleSearchQuery,
    SampleUpdateInput,
)
from app.services import events as event_service
from app.services import storage as storage_service


STUDY_ROLE_VALUES = ("current", "retired")
CUSTODY_VALUES = ("in_storage", "unplaced", "out_for_analysis", "archived")
USAGE_VALUES = ("unused", "used")


class SampleError(Exception):
    pass


def list_sample_types(db: Session) -> list[models.SampleType]:
    return sample_repository.list_sample_types(db)


def list_studies(db: Session) -> list[models.Study]:
    return sample_repository.list_studies(db)


def search_samples(db: Session, query: SampleSearchQuery) -> list[SampleListItem]:
    return [_build_list_item(sample) for sample in sample_repository.search(db, query)]


def list_sample_items_by_ids(db: Session, sample_ids: list[int]) -> list[SampleListItem]:
    return [_build_list_item(sample) for sample in sample_repository.get_by_ids(db, sample_ids)]


def get_filter_options(db: Session, query: SampleSearchQuery, column: str) -> SampleFilterOptionsResponse:
    scoped_query = _without_column_filter(query, column)
    rows = search_samples(db, scoped_query)
    selected_values = _selected_values_for_column(query, column)
    options: list[SampleFilterOption] = []

    if column == "sample_type":
        counts: dict[tuple[str, str], int] = {}
        for row in rows:
            if row.sample_type_id is None or not row.sample_type_name:
                continue
            key = (str(row.sample_type_id), row.sample_type_name)
            counts[key] = counts.get(key, 0) + 1
        options = [
            SampleFilterOption(value=value, label=label, count=count, selected=value in selected_values)
            for (value, label), count in sorted(counts.items(), key=lambda item: item[0][1].lower())
        ]
    elif column == "study":
        counts: dict[tuple[str, str], int] = {}
        for row in rows:
            if row.study_id is None or not row.study_name:
                continue
            label = row.study_name
            key = (str(row.study_id), label)
            counts[key] = counts.get(key, 0) + 1
        options = [
            SampleFilterOption(value=value, label=label, count=count, selected=value in selected_values)
            for (value, label), count in sorted(counts.items(), key=lambda item: item[0][1].lower())
        ]
    elif column == "study_role":
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.study_role] = counts.get(row.study_role, 0) + 1
        options = [
            SampleFilterOption(value=value, label=_study_role_label(value), count=count, selected=value in selected_values)
            for value, count in sorted(counts.items(), key=lambda item: item[0])
        ]
    elif column == "custody":
        counts: dict[str, int] = {}
        for row in rows:
            key = _normalize_label_value(row.custody_label)
            counts[key] = counts.get(key, 0) + 1
        options = [
            SampleFilterOption(value=value, label=_labelize(value), count=count, selected=value in selected_values)
            for value, count in sorted(counts.items(), key=lambda item: item[0])
        ]
    elif column == "usage":
        counts: dict[str, int] = {}
        for row in rows:
            key = _normalize_label_value(row.usage_label)
            counts[key] = counts.get(key, 0) + 1
        options = [
            SampleFilterOption(value=value, label=_labelize(value), count=count, selected=value in selected_values)
            for value, count in sorted(counts.items(), key=lambda item: item[0])
        ]
    elif column == "visit_label":
        counts: dict[str, int] = {}
        for row in rows:
            if not row.visit_label:
                continue
            counts[row.visit_label] = counts.get(row.visit_label, 0) + 1
        options = [
            SampleFilterOption(value=value, label=value, count=count, selected=value in selected_values)
            for value, count in sorted(counts.items(), key=lambda item: item[0].lower())
        ]
    elif column == "timepoint_label":
        counts: dict[str, int] = {}
        for row in rows:
            if not row.timepoint_label:
                continue
            counts[row.timepoint_label] = counts.get(row.timepoint_label, 0) + 1
        options = [
            SampleFilterOption(value=value, label=value, count=count, selected=value in selected_values)
            for value, count in sorted(counts.items(), key=lambda item: item[0].lower())
        ]
    elif column == "location":
        placed = sum(1 for row in rows if row.location_path)
        unplaced = len(rows) - placed
        options = [
            SampleFilterOption(value="placed", label="Placed", count=placed, selected="placed" in selected_values),
            SampleFilterOption(value="unplaced", label="Unplaced", count=unplaced, selected="unplaced" in selected_values),
        ]

    return SampleFilterOptionsResponse(column=column, options=options)


def recent_samples(db: Session, limit: int = 8) -> list[SampleListItem]:
    return [_build_list_item(sample) for sample in sample_repository.recent(db, limit=limit)]


def get_sample_detail(db: Session, sample_id: int) -> SampleDetailView | None:
    sample = sample_repository.get_by_id(db, sample_id)
    if sample is None:
        return None
    sample_events = event_service.list_events(db, limit=25, sample_id=sample.id)
    return _build_detail_view(sample, sample_events)


def create_sample(
    db: Session,
    data: SampleCreateInput,
    user: models.User | None,
    *,
    commit: bool = True,
    event_payload: dict | None = None,
) -> models.Sample:
    sample_identifier = data.sample_id.strip()
    if not sample_identifier:
        raise SampleError("Sample ID is required")
    visit_label = _normalize_numeric_label(data.visit_label, "Visit")
    timepoint_label = _normalize_numeric_label(data.timepoint_label, "Timepoint")
    if sample_repository.get_by_identity(
        db,
        sample_identifier,
        data.sample_type_id,
        visit_label,
        timepoint_label,
        data.aliquot_number,
    ) is not None:
        raise SampleError("A sample with this ID, type, visit, timepoint, and aliquot already exists")
    _validate_reference_fields(db, data.sample_type_id, data.study_id)
    sample = models.Sample(
        sample_id=sample_identifier,
        study_role=models.StudyRole(data.study_role),
        is_archived=False,
        is_out_for_analysis=False,
        volume=data.volume,
        volume_units=_normalize_units(data.volume_units),
        sample_type_id=data.sample_type_id,
        study_id=data.study_id,
        visit_label=visit_label,
        timepoint_label=timepoint_label,
        aliquot_number=data.aliquot_number,
        hemolysis_classification=_normalize_hemolysis(data.hemolysis_classification),
        thaw_count=max(data.thaw_count, 0),
        notes=_normalize_optional(data.notes),
        collection_at=data.collection_at,
    )
    db.add(sample)
    db.flush()
    db.refresh(sample)
    create_event_payload = {
        "sample_id": sample.sample_id,
        "study_role": sample.study_role.value,
        "snapshot": _sample_audit_snapshot(sample),
    }
    if event_payload:
        create_event_payload.update(event_payload)
    _log_event(
        db,
        event_type=models.EventType.create_sample,
        user=user,
        sample=sample,
        payload=create_event_payload,
    )
    _finalize(db, sample, commit)
    return sample


def update_sample(
    db: Session,
    sample_id: int,
    data: SampleUpdateInput,
    user: models.User | None,
    *,
    commit: bool = True,
    event_payload: dict | None = None,
) -> models.Sample:
    sample = sample_repository.get_by_id(db, sample_id)
    if sample is None:
        raise SampleError("Sample not found")
    before_snapshot = _sample_audit_snapshot(sample)
    payload = data.model_dump(exclude_unset=True)
    _validate_reference_fields(db, payload.get("sample_type_id"), payload.get("study_id"))

    field_map = {
        "sample_type_id": lambda value: value,
        "study_id": lambda value: value,
        "visit_label": lambda value: _normalize_numeric_label(value, "Visit"),
        "timepoint_label": lambda value: _normalize_numeric_label(value, "Timepoint"),
        "aliquot_number": lambda value: value,
        "hemolysis_classification": _normalize_hemolysis,
        "study_role": lambda value: models.StudyRole(value) if value is not None else None,
        "volume": lambda value: value,
        "volume_units": _normalize_units,
        "thaw_count": lambda value: max(value, 0) if value is not None else None,
        "notes": _normalize_optional,
        "collection_at": lambda value: value,
    }
    for field_name, normalizer in field_map.items():
        if field_name in payload:
            setattr(sample, field_name, normalizer(payload[field_name]))

    if sample_repository.get_by_identity(
        db,
        sample.sample_id,
        sample.sample_type_id,
        sample.visit_label,
        sample.timepoint_label,
        sample.aliquot_number,
        exclude_sample_pk=sample.id,
    ) is not None:
        raise SampleError("A sample with this ID, type, visit, timepoint, and aliquot already exists")

    _validate_sample_custody(sample)
    db.flush()
    db.refresh(sample)
    after_snapshot = _sample_audit_snapshot(sample)
    changes = _sample_snapshot_changes(before_snapshot, after_snapshot)
    db.add(sample)
    if changes:
        update_event_payload = {
            "before": before_snapshot,
            "after": after_snapshot,
            "changes": changes,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if event_payload:
            update_event_payload.update(event_payload)
        _log_event(
            db,
            event_type=models.EventType.update_sample,
            user=user,
            sample=sample,
            payload=update_event_payload,
        )
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(sample)
    return sample


def add_note_entry(
    db: Session,
    sample_id: int,
    data: SampleNoteCreateInput,
    user: models.User | None,
) -> models.SampleNoteEntry:
    sample = sample_repository.get_by_id(db, sample_id)
    if sample is None:
        raise SampleError("Sample not found")
    text = (data.text or "").strip()
    if not text:
        raise SampleError("Note text is required")
    note_entry = models.SampleNoteEntry(sample_id=sample.id, user_id=user.id if user else None, text=text)
    sample.updated_at = datetime.utcnow()
    db.add(sample)
    db.add(note_entry)
    _log_event(
        db,
        event_type=models.EventType.add_note,
        user=user,
        sample=sample,
        payload={"text": text},
    )
    db.commit()
    db.refresh(note_entry)
    return note_entry


def place_sample(
    db: Session,
    sample_id: int,
    data: PlaceSampleInput,
    user: models.User | None,
    *,
    commit: bool = True,
    event_payload: dict | None = None,
) -> models.SampleLocation:
    sample = sample_repository.get_by_id(db, sample_id)
    if sample is None:
        raise SampleError("Sample not found")
    position = storage_service.get_position(db, data.position_id)
    if position is None:
        raise SampleError("Position not found")
    return _place_or_move(db, sample, position, user, commit=commit, event_payload=event_payload)


def move_sample(
    db: Session,
    sample_id: int,
    data: MoveSampleInput,
    user: models.User | None,
    *,
    commit: bool = True,
    event_payload: dict | None = None,
) -> models.SampleLocation:
    sample = sample_repository.get_by_id(db, sample_id)
    if sample is None:
        raise SampleError("Sample not found")
    if sample.location is None:
        raise SampleError("Sample has no current location")
    position = storage_service.get_position(db, data.to_position_id)
    if position is None:
        raise SampleError("Destination position not found")
    return _place_or_move(db, sample, position, user, commit=commit, event_payload=event_payload)


def retrieve_sample(
    db: Session,
    sample_id: int,
    data: RetrieveSampleInput,
    user: models.User | None,
) -> models.Sample:
    sample = sample_repository.get_by_id(db, sample_id)
    if sample is None:
        raise SampleError("Sample not found")
    before_snapshot = _sample_audit_snapshot(sample)
    from_position_id = None
    from_path = None
    if sample.location:
        from_position_id = sample.location.position_id
        from_path = storage_service.storage_path_for_position(sample.location.position)
        db.delete(sample.location)
        sample.location = None
    sample.is_archived = True
    sample.is_out_for_analysis = False
    sample.updated_at = datetime.utcnow()
    _validate_sample_custody(sample)
    db.add(sample)
    if data.note:
        db.add(models.SampleNoteEntry(sample_id=sample.id, user_id=user.id if user else None, text=data.note.strip()))
    after_snapshot = _sample_audit_snapshot(sample)
    _log_event(
        db,
        event_type=models.EventType.status_change,
        user=user,
        sample=sample,
        from_position_id=from_position_id,
        payload={
            "before": before_snapshot,
            "after": after_snapshot,
            "changes": _sample_snapshot_changes(before_snapshot, after_snapshot),
            "note": data.note,
            "from_path": from_path,
            "to_custody": after_snapshot.get("custody"),
        },
    )
    db.commit()
    db.refresh(sample)
    return sample


def delete_sample(
    db: Session,
    sample_id: int,
    user: models.User | None,
) -> None:
    sample = sample_repository.get_by_id(db, sample_id)
    if sample is None:
        raise SampleError("Sample not found")

    location = sample.location
    location_path = storage_service.storage_path_for_position(location.position) if location else None
    location_label = location.position.label if location else None
    from_position_id = location.position_id if location else None

    for event in list(sample.events):
        payload = dict(event.payload)
        payload.setdefault("sample_identifier", sample.sample_id)
        payload.setdefault("sample_pk", sample.id)
        event.sample_id = None
        event.set_payload(payload)
        db.add(event)

    if location is not None:
        db.delete(location)

    delete_event = models.Event(
        event_type=models.EventType.delete_sample,
        user_id=user.id if user else None,
        sample_id=None,
        from_position_id=from_position_id,
        created_at=datetime.utcnow(),
    )
    delete_event.set_payload(
        {
            "sample_pk": sample.id,
            "sample_identifier": sample.sample_id,
            "study_role": sample.study_role.value,
            "is_archived": sample.is_archived,
            "is_out_for_analysis": sample.is_out_for_analysis,
            "sample_type": sample.sample_type.name if sample.sample_type else None,
            "study": sample.study.display_name if sample.study else None,
            "visit": sample.visit_label,
            "timepoint": sample.timepoint_label,
            "aliquot": str(sample.aliquot_number) if sample.aliquot_number is not None else None,
            "hemolysis": str(sample.hemolysis_classification) if sample.hemolysis_classification is not None else None,
            "volume": _volume_display(sample.volume, sample.volume_units),
            "thaw_count": str(sample.thaw_count),
            "notes": sample.notes or None,
            "collection": sample.collection_at.strftime("%m/%d/%y %H:%M") if sample.collection_at else None,
            "snapshot": _sample_audit_snapshot(sample),
            "location_path": location_path,
            "location_label": location_label,
        }
    )
    db.add(delete_event)
    db.delete(sample)
    db.commit()


def derive_custody(sample: models.Sample | None) -> str:
    if sample is None:
        return "unknown"
    if sample.is_archived:
        return "archived"
    if sample.is_out_for_analysis:
        return "out_for_analysis"
    if sample.location is not None:
        return "in_storage"
    return "unplaced"


def derive_usage(sample: models.Sample | None) -> str:
    if sample is None:
        return "unknown"
    return "used" if sample.thaw_count > 0 else "unused"


def _build_list_item(sample: models.Sample) -> SampleListItem:
    location_label = sample.location.position.label if sample.location else None
    location_path = storage_service.storage_path_for_position(sample.location.position) if sample.location else None
    return SampleListItem(
        id=sample.id,
        sample_id=sample.sample_id,
        study_role=sample.study_role.value,
        is_archived=sample.is_archived,
        is_out_for_analysis=sample.is_out_for_analysis,
        custody_label=_labelize(derive_custody(sample)),
        usage_label=_labelize(derive_usage(sample)),
        volume=sample.volume,
        volume_units=sample.volume_units,
        thaw_count=sample.thaw_count,
        hemolysis_classification=sample.hemolysis_classification,
        created_at=sample.created_at,
        updated_at=sample.updated_at,
        collection_at=sample.collection_at,
        sample_type_id=sample.sample_type_id,
        sample_type_name=sample.sample_type.name if sample.sample_type else None,
        study_id=sample.study_id,
        study_name=sample.study.name if sample.study else None,
        visit_label=sample.visit_label,
        timepoint_label=sample.timepoint_label,
        aliquot_number=sample.aliquot_number,
        location_label=location_label,
        location_path=location_path,
        location_position_id=sample.location.position_id if sample.location else None,
    )


def _build_detail_view(sample: models.Sample, sample_events: list[EventView]) -> SampleDetailView:
    location_label = sample.location.position.label if sample.location else None
    location_path = storage_service.storage_path_for_position(sample.location.position) if sample.location else None
    note_entries = sorted(sample.note_entries, key=lambda item: item.created_at, reverse=True)
    return SampleDetailView(
        id=sample.id,
        sample_id=sample.sample_id,
        study_role=sample.study_role.value,
        is_archived=sample.is_archived,
        is_out_for_analysis=sample.is_out_for_analysis,
        custody_label=_labelize(derive_custody(sample)),
        usage_label=_labelize(derive_usage(sample)),
        volume=sample.volume,
        volume_units=sample.volume_units,
        thaw_count=sample.thaw_count,
        notes=sample.notes,
        sample_type_id=sample.sample_type_id,
        sample_type_name=sample.sample_type.name if sample.sample_type else None,
        study_id=sample.study_id,
        study_name=sample.study.name if sample.study else None,
        visit_label=sample.visit_label,
        timepoint_label=sample.timepoint_label,
        aliquot_number=sample.aliquot_number,
        hemolysis_classification=sample.hemolysis_classification,
        collection_at=sample.collection_at,
        created_at=sample.created_at,
        updated_at=sample.updated_at,
        location_label=location_label,
        location_path=location_path,
        location_position_id=sample.location.position_id if sample.location else None,
        note_entries=[_build_note_entry_view(entry) for entry in note_entries],
        events=sample_events,
    )


def _build_note_entry_view(entry: models.SampleNoteEntry) -> SampleNoteEntryView:
    return SampleNoteEntryView(
        id=entry.id,
        sample_id=entry.sample_id,
        user_id=entry.user_id,
        username=entry.user.username if entry.user else None,
        text=entry.text,
        created_at=entry.created_at,
    )


def _place_or_move(
    db: Session,
    sample: models.Sample,
    position: models.StoragePosition,
    user: models.User | None,
    *,
    commit: bool = True,
    event_payload: dict | None = None,
) -> models.SampleLocation:
    if sample.is_archived:
        raise SampleError("Archived samples cannot be placed")
    if sample.is_out_for_analysis:
        raise SampleError("Samples out for analysis cannot be placed until they are returned")
    if position.location:
        raise SampleError("Position already occupied")
    existing_location = sample.location
    from_path = storage_service.storage_path_for_position(existing_location.position) if existing_location else None
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
    sample.updated_at = datetime.utcnow()
    _validate_sample_custody(sample)
    db.add(sample)
    move_event_payload = {
        "position_id": position.id,
        "from_path": from_path,
        "to_path": storage_service.storage_path_for_position(position),
    }
    if event_payload:
        move_event_payload.update(event_payload)
    _log_event(
        db,
        event_type=event_type,
        user=user,
        sample=sample,
        from_position_id=from_position_id,
        to_position_id=position.id,
        payload=move_event_payload,
    )
    _finalize(db, existing_location, commit)
    return existing_location


def _validate_reference_fields(db: Session, sample_type_id: int | None, study_id: int | None) -> None:
    if sample_type_id and sample_repository.get_sample_type(db, sample_type_id) is None:
        raise SampleError("Sample type not found")
    if study_id and sample_repository.get_study(db, study_id) is None:
        raise SampleError("Study not found")


def _validate_sample_custody(sample: models.Sample) -> None:
    if sample.is_archived and sample.is_out_for_analysis:
        raise SampleError("A sample cannot be archived and out for analysis at the same time")
    if sample.is_archived and sample.location is not None:
        raise SampleError("Archived samples cannot have a storage location")
    if sample.is_out_for_analysis and sample.location is not None:
        raise SampleError("Samples out for analysis cannot keep a storage location")


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_numeric_label(value: str | None, field_label: str) -> str | None:
    normalized = _normalize_optional(value)
    if normalized is None:
        return None
    if not re.fullmatch(r"\d+", normalized):
        raise SampleError(f"{field_label} must contain numbers only")
    return normalized


def _normalize_units(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    return normalized or "mL"


def _normalize_hemolysis(value: float | int | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric < 1 or numeric > 7:
        raise SampleError("Hemolysis must be between 1 and 7 in 0.5 increments")
    doubled = numeric * 2
    rounded = round(doubled)
    if not math.isclose(doubled, rounded, abs_tol=1e-9):
        raise SampleError("Hemolysis must be between 1 and 7 in 0.5 increments")
    return rounded / 2


def _sample_audit_snapshot(sample: models.Sample) -> dict[str, str]:
    return {
        "sample_id": sample.sample_id,
        "type": sample.sample_type.name if sample.sample_type else "--",
        "study": sample.study.display_name if sample.study else "--",
        "visit": sample.visit_label or "--",
        "timepoint": sample.timepoint_label or "--",
        "aliquot": str(sample.aliquot_number) if sample.aliquot_number is not None else "--",
        "hemolysis": str(sample.hemolysis_classification) if sample.hemolysis_classification is not None else "--",
        "study_role": sample.study_role.value,
        "custody": derive_custody(sample),
        "usage": derive_usage(sample),
        "volume": _volume_display(sample.volume, sample.volume_units),
        "thaw_count": str(sample.thaw_count),
        "notes": sample.notes or "--",
        "collection": sample.collection_at.strftime("%m/%d/%y %H:%M") if sample.collection_at else "--",
    }


def _sample_snapshot_changes(before: dict[str, str], after: dict[str, str]) -> list[dict[str, str]]:
    field_labels = {
        "type": "Type",
        "study": "Study",
        "visit": "Visit",
        "timepoint": "Timepoint",
        "aliquot": "Aliquot",
        "hemolysis": "Hemolysis",
        "study_role": "Study Role",
        "custody": "Custody",
        "usage": "Usage",
        "volume": "Volume",
        "thaw_count": "Thaw Count",
        "notes": "Notes",
        "collection": "Collection",
    }
    changes: list[dict[str, str]] = []
    for field, label in field_labels.items():
        before_value = before.get(field, "--")
        after_value = after.get(field, "--")
        if before_value != after_value:
            changes.append(
                {
                    "field": field,
                    "label": label,
                    "before": _display_change_value(field, before_value),
                    "after": _display_change_value(field, after_value),
                }
            )
    return changes


def _display_change_value(field: str, value: str) -> str:
    if field == "study_role":
        return _study_role_label(value)
    if field in {"custody", "usage"}:
        return _labelize(value)
    return value


def _study_role_label(value: str | None) -> str:
    if not value:
        return "--"
    return "Current" if value == "current" else "Retired"


def _labelize(value: str | None) -> str:
    if not value:
        return "--"
    return value.replace("_", " ")


def _normalize_label_value(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _volume_display(volume: float | None, units: str | None) -> str:
    if volume is None:
        return "--"
    return f"{volume:g} {units or 'mL'}"


def _without_column_filter(query: SampleSearchQuery, column: str) -> SampleSearchQuery:
    scoped = query.model_copy(deep=True)
    if column == "sample_type":
        scoped.sample_type_id = None
        scoped.sample_type_ids = []
    elif column == "study":
        scoped.study_id = None
        scoped.study_ids = []
    elif column == "study_role":
        scoped.study_role = None
        scoped.study_roles = []
    elif column == "custody":
        scoped.custody = None
        scoped.custodies = []
    elif column == "usage":
        scoped.usage = None
        scoped.usages = []
    elif column == "visit_label":
        scoped.visit_label = None
        scoped.visit_labels = []
    elif column == "timepoint_label":
        scoped.timepoint_label = None
        scoped.timepoint_labels = []
    elif column == "location":
        scoped.location_state = None
        scoped.storage_node_ids = []
    return scoped


def _selected_values_for_column(query: SampleSearchQuery, column: str) -> set[str]:
    if column == "sample_type":
        return {str(value) for value in _merged_values(query.sample_type_ids, query.sample_type_id)}
    if column == "study":
        return {str(value) for value in _merged_values(query.study_ids, query.study_id)}
    if column == "study_role":
        return {str(value) for value in _merged_values(query.study_roles, query.study_role)}
    if column == "custody":
        return {str(value) for value in _merged_values(query.custodies, query.custody)}
    if column == "usage":
        return {str(value) for value in _merged_values(query.usages, query.usage)}
    if column == "visit_label":
        return {str(value) for value in _merged_values(query.visit_labels, query.visit_label)}
    if column == "timepoint_label":
        return {str(value) for value in _merged_values(query.timepoint_labels, query.timepoint_label)}
    if column == "location":
        selected: set[str] = set()
        if query.location_state:
            selected.add(query.location_state)
        selected.update(str(value) for value in query.storage_node_ids)
        return selected
    return set()


def _merged_values(values: list, single):
    merged = list(values or [])
    if single is not None and single not in merged:
        merged.append(single)
    return merged


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
    sample: models.Sample,
    payload: dict,
    from_position_id: int | None = None,
    to_position_id: int | None = None,
) -> None:
    event = models.Event(
        event_type=event_type,
        user_id=user.id if user else None,
        sample_id=sample.id,
        from_position_id=from_position_id,
        to_position_id=to_position_id,
        created_at=datetime.utcnow(),
    )
    event.set_payload(payload)
    db.add(event)
