from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    BulkSampleImportCommitInput,
    MoveSampleInput,
    PlaceSampleInput,
    RetrieveSampleInput,
    SampleCreateInput,
    SampleFilterOptionsRequest,
    SampleNoteCreateInput,
    SampleSearchQuery,
    SampleUpdateInput,
)
from app.services import auth as auth_service
from app.services import bulk_imports as bulk_import_service
from app.services import samples as sample_service
from app.web.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/api/samples", tags=["samples"])


@router.get("/")
async def list_samples(
    request: Request,
    db: Session = Depends(get_db),
):
    _ = get_current_user(request, db)
    return sample_service.search_samples(db, _build_search_query(request))


@router.get("/selection-preview")
async def selection_preview(request: Request, db: Session = Depends(get_db)):
    _ = get_current_user(request, db)
    sample_ids = _parse_int_list(request.query_params.getlist("sample_ids"))
    return sample_service.list_sample_items_by_ids(db, sample_ids)


@router.post("/filter-options")
async def sample_filter_options(
    payload: SampleFilterOptionsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _ = get_current_user(request, db)
    return sample_service.get_filter_options(db, payload.filters, payload.column)


@router.post("/")
async def create_sample(payload: SampleCreateInput, request: Request, db: Session = Depends(get_db)):
    try:
        user = require_permission("edit_samples")(request, db)
        sample = sample_service.create_sample(db, payload, user)
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sample_service.get_sample_detail(db, sample.id)


@router.post("/bulk/preview")
async def bulk_preview(payload: BulkSampleImportCommitInput, request: Request, db: Session = Depends(get_db)):
    _ = require_permission("bulk_import_samples")(request, db)
    return bulk_import_service.preview_sample_import(db, payload.raw_payload, payload.target_box_id)


@router.post("/bulk/preview-upload")
async def bulk_preview_upload(
    request: Request,
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _ = require_permission("bulk_import_samples")(request, db)
    file_bytes = await import_file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Upload a completed Excel template.")
    filename = str(import_file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Bulk add only accepts .xlsx workbooks.")
    raw_payload = bulk_import_service.sample_workbook_to_csv(file_bytes)
    return bulk_import_service.preview_sample_import(db, raw_payload, None)


@router.post("/bulk/commit")
async def bulk_commit(payload: BulkSampleImportCommitInput, request: Request, db: Session = Depends(get_db)):
    user = require_permission("bulk_import_samples")(request, db)
    return bulk_import_service.commit_sample_import(db, payload, user)


@router.get("/{sample_id}")
async def get_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    _ = get_current_user(request, db)
    sample = sample_service.get_sample_detail(db, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@router.put("/{sample_id}")
async def update_sample(sample_id: int, payload: SampleUpdateInput, request: Request, db: Session = Depends(get_db)):
    try:
        user = require_permission("edit_samples")(request, db)
        sample_service.update_sample(db, sample_id, payload, user)
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sample = sample_service.get_sample_detail(db, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@router.post("/{sample_id}/notes")
async def add_note(sample_id: int, payload: SampleNoteCreateInput, request: Request, db: Session = Depends(get_db)):
    try:
        user = require_permission("edit_samples")(request, db)
        sample_service.add_note_entry(db, sample_id, payload, user)
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sample = sample_service.get_sample_detail(db, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@router.post("/{sample_id}/place")
async def place_sample(sample_id: int, payload: PlaceSampleInput, request: Request, db: Session = Depends(get_db)):
    try:
        user = require_permission("place_move_samples")(request, db)
        sample_service.place_sample(db, sample_id, payload, user)
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/{sample_id}/move")
async def move_sample(sample_id: int, payload: MoveSampleInput, request: Request, db: Session = Depends(get_db)):
    try:
        user = require_permission("place_move_samples")(request, db)
        sample_service.move_sample(db, sample_id, payload, user)
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/{sample_id}/retrieve")
async def retrieve_sample(sample_id: int, payload: RetrieveSampleInput, request: Request, db: Session = Depends(get_db)):
    try:
        user = require_permission("archive_samples")(request, db)
        sample_service.retrieve_sample(db, sample_id, payload, user)
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sample = sample_service.get_sample_detail(db, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@router.delete("/{sample_id}")
async def delete_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    try:
        auth_service.require_permission(user, "delete_samples")
        sample_service.delete_sample(db, sample_id, user)
    except auth_service.PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return datetime.strptime(normalized, "%m/%d/%y %H:%M")
    except ValueError:
        return None


def _parse_optional_bool(value: str | None) -> bool | None:
    normalized = _normalize_text(value)
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _parse_int(value: str | None) -> int | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _parse_int_list(values) -> list[int]:
    parsed: list[int] = []
    for value in values:
        number = _parse_int(value)
        if number is not None and number not in parsed:
            parsed.append(number)
    return parsed


def _parse_text_list(values) -> list[str]:
    parsed: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if normalized and normalized not in parsed:
            parsed.append(normalized)
    return parsed


def _parse_study_role_list(values) -> list[str]:
    parsed: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if normalized in {"current", "retired"} and normalized not in parsed:
            parsed.append(normalized)
    return parsed


def _parse_custody_list(values) -> list[str]:
    parsed: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if normalized in {"in_storage", "unplaced", "out_for_analysis", "archived"} and normalized not in parsed:
            parsed.append(normalized)
    return parsed


def _parse_usage_list(values) -> list[str]:
    parsed: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if normalized in {"used", "unused"} and normalized not in parsed:
            parsed.append(normalized)
    return parsed


def _build_search_query(request: Request) -> SampleSearchQuery:
    params = request.query_params
    return SampleSearchQuery(
        q=params.get("q", ""),
        sample_type_id=_parse_int(params.get("sample_type_id")),
        sample_type_ids=_parse_int_list(params.getlist("sample_type_ids")),
        study_id=_parse_int(params.get("study_id")),
        study_ids=_parse_int_list(params.getlist("study_ids")),
        study_role=_normalize_text(params.get("study_role")),
        study_roles=_parse_study_role_list(params.getlist("study_roles")),
        custody=_normalize_text(params.get("custody")),
        custodies=_parse_custody_list(params.getlist("custodies")),
        usage=_normalize_text(params.get("usage")),
        usages=_parse_usage_list(params.getlist("usages")),
        location_state=_normalize_text(params.get("location_state")),
        storage_node_ids=_parse_int_list(params.getlist("storage_node_ids")),
        visit_label=_normalize_text(params.get("visit_label")),
        visit_labels=_parse_text_list(params.getlist("visit_labels")),
        timepoint_label=_normalize_text(params.get("timepoint_label")),
        timepoint_labels=_parse_text_list(params.getlist("timepoint_labels")),
        aliquot_number=_parse_int(params.get("aliquot_number")),
        aliquot_min=_parse_int(params.get("aliquot_min")),
        aliquot_max=_parse_int(params.get("aliquot_max")),
        hemolysis_classification=_parse_float(params.get("hemolysis_classification")),
        hemolysis_min=_parse_float(params.get("hemolysis_min")),
        hemolysis_max=_parse_float(params.get("hemolysis_max")),
        thaw_count_min=_parse_int(params.get("thaw_count_min")),
        thaw_count_max=_parse_int(params.get("thaw_count_max")),
        volume_min=_parse_float(params.get("volume_min")),
        volume_max=_parse_float(params.get("volume_max")),
        collection_from=_parse_datetime(params.get("collection_from")),
        collection_to=_parse_datetime(params.get("collection_to")),
        registered_from=_parse_datetime(params.get("registered_from")),
        registered_to=_parse_datetime(params.get("registered_to")),
        updated_from=_parse_datetime(params.get("updated_from")),
        updated_to=_parse_datetime(params.get("updated_to")),
        has_notes=_parse_optional_bool(params.get("has_notes")),
        sort=_normalize_sort(params.get("sort")),
        sort_dir=_normalize_sort_dir(params.get("sort_dir")),
    )


def _normalize_sort(value: str | None) -> str:
    valid = {
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
    }
    normalized = _normalize_text(value)
    return normalized if normalized in valid else "sample_id"


def _normalize_sort_dir(value: str | None) -> str:
    normalized = _normalize_text(value)
    return normalized if normalized in {"asc", "desc"} else "asc"
