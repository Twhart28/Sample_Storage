from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    BulkSampleImportCommitInput,
    MoveSampleInput,
    PlaceSampleInput,
    RetrieveSampleInput,
    SampleCreateInput,
    SampleNoteCreateInput,
    SampleSearchQuery,
    SampleUpdateInput,
)
from app.services import sample_actions as sample_actions_service
from app.services import bulk_imports as bulk_import_service
from app.services import auth as auth_service
from app.services import samples as sample_service
from app.services import storage as storage_service
from app.web.dependencies import get_current_user, require_permission, templates

router = APIRouter()
DISPLAY_DATETIME_FORMAT = "%m/%d/%y %H:%M"
DEFAULT_VISIBLE_COLUMNS = [
    "sample_id",
    "study",
    "sample_type",
    "study_role",
    "volume",
    "location",
    "visit_label",
    "timepoint_label",
    "thaw_count",
    "updated_at",
]
TABLE_COLUMNS = [
    {"key": "sample_id", "label": "ID", "filter": "sort-only"},
    {"key": "study", "label": "Study", "filter": "options"},
    {"key": "sample_type", "label": "Type", "filter": "options"},
    {"key": "study_role", "label": "Study Role", "filter": "options"},
    {"key": "volume", "label": "Volume", "filter": "range-number"},
    {"key": "location", "label": "Location", "filter": "location"},
    {"key": "visit_label", "label": "Visit", "filter": "options"},
    {"key": "timepoint_label", "label": "Timepoint", "filter": "options"},
    {"key": "aliquot_number", "label": "Aliquot", "filter": "range-number"},
    {"key": "hemolysis_classification", "label": "Hemolysis", "filter": "range-number"},
    {"key": "thaw_count", "label": "Thaw Count", "filter": "range-number"},
    {"key": "collection_at", "label": "Collection", "filter": "range-date"},
    {"key": "created_at", "label": "Registered", "filter": "range-date"},
    {"key": "updated_at", "label": "Updated", "filter": "range-date"},
]
LABEL_HELP = {
    "id": "Participant ID",
    "type": "Sample Type",
    "study": "Study",
    "visit": "Visit Label",
    "timepoint": "Timepoint Label",
    "aliquot": "Aliquot Number",
    "hemolysis": "Hemolysis Classification #",
    "study_role": "Current role of the sample in the study record",
    "volume": "Current Remaining Volume",
    "registered": "Registered At",
    "updated": "Last Updated At",
    "notes": "Summary Note",
    "collection": "Collection Date and Time",
}


@router.get("/samples")
async def list_samples(
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    filters = _build_search_query(request)
    initial_rows = [sample.model_dump(mode="json") for sample in sample_service.search_samples(db, filters)]
    available_actions = sample_actions_service.available_actions(current_user)
    return templates.TemplateResponse(
        "samples_list.html",
        {
            "request": request,
            "current_user": current_user,
            "bootstrap": {
                "columns": TABLE_COLUMNS,
                "default_visible_columns": DEFAULT_VISIBLE_COLUMNS,
                "initial_rows": initial_rows,
                "initial_state": filters.model_dump(mode="json"),
                "search_endpoint": "/api/samples/",
                "filter_options_endpoint": "/api/samples/filter-options",
                "storage_tree": [node.model_dump(mode="json") for node in storage_service.list_storage_tree(db)],
                "sample_actions": available_actions,
                "can_use_sample_actions": bool(available_actions),
                "sample_actions_workspace_url": sample_actions_service.WORKSPACE_URL,
                "sample_actions_storage_key": sample_actions_service.SELECTION_STORAGE_KEY,
            },
            "label_help": LABEL_HELP,
        },
    )


@router.get("/samples/new")
async def new_sample(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    return _render_sample_form(request, db, current_user=current_user)


@router.post("/samples")
async def create_sample(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    form = await request.form()
    initial_values = _build_initial_values(overrides=form)
    payload = SampleCreateInput(
        sample_id=initial_values["sample_id"],
        sample_type_id=_parse_int(initial_values["sample_type_id"]),
        study_id=_parse_int(initial_values["study_id"]),
        visit_label=_normalize_text(initial_values["visit_label"]),
        timepoint_label=_normalize_text(initial_values["timepoint_label"]),
        aliquot_number=_parse_int(initial_values["aliquot_number"]),
        hemolysis_classification=_parse_int(initial_values["hemolysis_classification"]),
        study_role=initial_values["study_role"] or "current",
        volume=_parse_float(initial_values["volume"]),
        volume_units=_normalize_text(initial_values["volume_units"]) or "mL",
        thaw_count=_parse_int(initial_values["thaw_count"]) or 0,
        notes=_normalize_text(initial_values["notes"]),
        collection_at=_parse_datetime(initial_values["collection_at"]),
    )
    try:
        sample = sample_service.create_sample(db, payload, current_user)
    except sample_service.SampleError as exc:
        return _render_sample_form(
            request,
            db,
            current_user=current_user,
            error_message=str(exc),
            initial_values=initial_values,
            status_code=400,
        )
    return RedirectResponse(f"/samples/{sample.id}", status_code=303)


@router.get("/samples/bulk")
async def bulk_samples_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("bulk_import_samples")(request, db)
    return _render_bulk_samples_page(request, db, current_user=current_user)


@router.get("/samples/bulk/template")
async def bulk_samples_template(request: Request, db: Session = Depends(get_db)):
    _ = require_permission("bulk_import_samples")(request, db)
    sample_types = [sample_type.name for sample_type in sample_service.list_sample_types(db)]
    studies = [study.name for study in sample_service.list_studies(db)]
    boxes = [box.name for box in storage_service.list_boxes(db)]
    return Response(
        content=bulk_import_service.sample_template_xlsx(sample_types=sample_types, studies=studies, boxes=boxes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sample-import-template.xlsx"'},
    )


@router.get("/samples/bulk/template.csv")
async def bulk_samples_template_csv(current_user=Depends(require_permission("bulk_import_samples"))):
    _ = current_user
    return Response(
        content=bulk_import_service.sample_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample-import-template.csv"'},
    )


@router.post("/samples/bulk/preview")
async def bulk_samples_preview(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("bulk_import_samples")(request, db)
    form = await request.form()
    raw_payload = await _extract_bulk_payload(form)
    preview = bulk_import_service.preview_sample_import(db, raw_payload, None)
    return _render_bulk_samples_page(
        request,
        db,
        current_user=current_user,
        raw_payload=raw_payload,
        preview=preview,
    )


@router.post("/samples/bulk/commit")
async def bulk_samples_commit(request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("bulk_import_samples")(request, db)
    form = await request.form()
    raw_payload = str(form.get("raw_payload") or "")
    result = bulk_import_service.commit_sample_import(
        db,
        BulkSampleImportCommitInput(raw_payload=raw_payload, target_box_id=None),
        current_user,
    )
    return _render_bulk_samples_page(
        request,
        db,
        current_user=current_user,
        raw_payload=raw_payload,
        result=result,
    )


@router.get("/samples/{sample_id}")
async def sample_detail(sample_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    sample = sample_service.get_sample_detail(db, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return templates.TemplateResponse(
        "samples_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "sample": sample,
            "boxes": storage_service.list_boxes(db),
            "label_help": LABEL_HELP,
            "can_edit_samples": auth_service.has_permission(current_user, "edit_samples"),
            "can_place_move_samples": auth_service.has_permission(current_user, "place_move_samples"),
            "can_use_sample_actions": sample_actions_service.has_any_actions(current_user),
            "can_archive_samples": auth_service.has_permission(current_user, "archive_samples"),
            "can_delete_samples": auth_service.has_permission(current_user, "delete_samples"),
        },
    )


@router.get("/samples/{sample_id}/edit")
async def edit_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    sample = sample_service.get_sample_detail(db, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return _render_sample_form(request, db, current_user=current_user, sample=sample)


@router.post("/samples/{sample_id}")
async def update_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    sample = sample_service.get_sample_detail(db, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    form = await request.form()
    initial_values = _build_initial_values(sample=sample, overrides=form)
    payload = SampleUpdateInput(
        sample_type_id=_parse_int(initial_values["sample_type_id"]),
        study_id=_parse_int(initial_values["study_id"]),
        visit_label=_normalize_text(initial_values["visit_label"]),
        timepoint_label=_normalize_text(initial_values["timepoint_label"]),
        aliquot_number=_parse_int(initial_values["aliquot_number"]),
        hemolysis_classification=_parse_int(initial_values["hemolysis_classification"]),
        study_role=initial_values["study_role"] or None,
        volume=_parse_float(initial_values["volume"]),
        volume_units=_normalize_text(initial_values["volume_units"]) or "mL",
        thaw_count=_parse_int(initial_values["thaw_count"]),
        notes=_normalize_text(initial_values["notes"]),
        collection_at=_parse_datetime(initial_values["collection_at"]),
    )
    try:
        sample_service.update_sample(db, sample_id, payload, current_user)
    except sample_service.SampleError as exc:
        return _render_sample_form(
            request,
            db,
            current_user=current_user,
            sample=sample,
            error_message=str(exc),
            initial_values=initial_values,
            status_code=400,
        )
    return RedirectResponse(f"/samples/{sample_id}", status_code=303)


@router.post("/samples/{sample_id}/notes")
async def add_sample_note(sample_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("edit_samples")(request, db)
    form = await request.form()
    try:
        sample_service.add_note_entry(
            db,
            sample_id,
            SampleNoteCreateInput(text=(form.get("text") or "").strip()),
            current_user,
        )
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/samples/{sample_id}", status_code=303)


@router.post("/samples/{sample_id}/place")
async def place_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("place_move_samples")(request, db)
    form = await request.form()
    try:
        sample_service.place_sample(
            db,
            sample_id,
            PlaceSampleInput(position_id=int(form.get("position_id"))),
            current_user,
        )
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/samples/{sample_id}", status_code=303)


@router.post("/samples/{sample_id}/move")
async def move_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("place_move_samples")(request, db)
    form = await request.form()
    try:
        sample_service.move_sample(
            db,
            sample_id,
            MoveSampleInput(to_position_id=int(form.get("to_position_id"))),
            current_user,
        )
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/samples/{sample_id}", status_code=303)


@router.post("/samples/{sample_id}/retrieve")
async def retrieve_sample(sample_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_permission("archive_samples")(request, db)
    form = await request.form()
    try:
        sample_service.retrieve_sample(
            db,
            sample_id,
            RetrieveSampleInput(note=_normalize_text(form.get("note"))),
            current_user,
        )
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/samples/{sample_id}", status_code=303)


@router.post("/samples/{sample_id}/delete")
async def delete_sample(
    sample_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("delete_samples")),
):
    _ = request
    try:
        sample_service.delete_sample(db, sample_id, current_user)
    except sample_service.SampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/samples", status_code=303)


def _render_sample_form(
    request: Request,
    db: Session,
    *,
    current_user,
    sample=None,
    error_message: str | None = None,
    initial_values: dict[str, str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "samples_form.html",
        {
            "request": request,
            "current_user": current_user,
            "sample": sample,
            "sample_types": sample_service.list_sample_types(db),
            "studies": sample_service.list_studies(db),
            "label_help": LABEL_HELP,
            "error_message": error_message,
            "initial_values": initial_values or _build_initial_values(sample=sample),
        },
        status_code=status_code,
    )


def _render_bulk_samples_page(
    request: Request,
    db: Session,
    *,
    current_user,
    raw_payload: str = "",
    preview=None,
    result=None,
):
    return templates.TemplateResponse(
        "samples_bulk.html",
        {
            "request": request,
            "current_user": current_user,
            "raw_payload": raw_payload,
            "preview": preview,
            "result": result,
            "template_headers": bulk_import_service.SAMPLE_HEADERS,
        },
    )


def _build_initial_values(sample=None, overrides=None) -> dict[str, str]:
    values = {
        "sample_id": sample.sample_id if sample else "",
        "sample_type_id": str(sample.sample_type_id) if sample and sample.sample_type_id is not None else "",
        "study_id": str(sample.study_id) if sample and sample.study_id is not None else "",
        "visit_label": sample.visit_label if sample and sample.visit_label else "",
        "timepoint_label": sample.timepoint_label if sample and sample.timepoint_label else "",
        "aliquot_number": str(sample.aliquot_number) if sample and sample.aliquot_number is not None else "",
        "hemolysis_classification": str(sample.hemolysis_classification) if sample and sample.hemolysis_classification is not None else "",
        "study_role": sample.study_role if sample else "current",
        "volume": str(sample.volume) if sample and sample.volume is not None else "",
        "volume_units": sample.volume_units if sample and sample.volume_units else "mL",
        "thaw_count": str(sample.thaw_count) if sample else "0",
        "notes": sample.notes if sample and sample.notes else "",
        "collection_at": format_datetime(sample.collection_at) if sample and sample.collection_at else "",
    }
    if overrides:
        for key in values:
            if key in overrides:
                values[key] = str(overrides.get(key) or "")
    return values


async def _extract_bulk_payload(form) -> str:
    raw_payload = str(form.get("raw_payload") or "")
    upload = form.get("csv_file")
    if upload is not None and getattr(upload, "filename", ""):
        file_bytes = await upload.read()
        if file_bytes:
            filename = str(getattr(upload, "filename", "")).lower()
            if filename.endswith(".xlsx"):
                return bulk_import_service.sample_workbook_to_csv(file_bytes)
            return file_bytes.decode("utf-8-sig")
    return raw_payload


def _parse_datetime(value) -> datetime | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return datetime.strptime(normalized, DISPLAY_DATETIME_FORMAT)
    except ValueError:
        return None


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime(DISPLAY_DATETIME_FORMAT)


def _parse_optional_bool(value) -> bool | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _parse_int(value) -> int | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except ValueError:
        return None


def _parse_float(value) -> float | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _normalize_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
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
        hemolysis_classification=_parse_int(params.get("hemolysis_classification")),
        hemolysis_min=_parse_int(params.get("hemolysis_min")),
        hemolysis_max=_parse_int(params.get("hemolysis_max")),
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


def _normalize_sort(value) -> str:
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


def _normalize_sort_dir(value) -> str:
    normalized = _normalize_text(value)
    return normalized if normalized in {"asc", "desc"} else "asc"
