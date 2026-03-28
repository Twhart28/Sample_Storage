from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from sqlalchemy.orm import Session

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.domain import models
from app.repositories import samples as sample_repository
from app.services import samples as sample_service
from app.services import storage as storage_service
from app.schemas import (
    BoxCreateInput,
    BulkBoxImportCommitInput,
    BulkBoxImportCommitResult,
    BulkBoxImportPreview,
    BulkBoxImportRow,
    BulkSampleImportCommitInput,
    BulkSampleImportCommitResult,
    BulkSampleImportPreview,
    BulkSampleImportRow,
    PlaceSampleInput,
    SampleCreateInput,
    StorageNodeCreate,
)

SAMPLE_HEADERS = [
    "sample_id",
    "sample_type",
    "study",
    "visit",
    "timepoint",
    "aliquot",
    "hemolysis",
    "study_role",
    "volume",
    "volume_units",
    "thaw_count",
    "notes",
    "collection_at",
    "box",
    "position",
]
BOX_HEADERS = [
    "parent",
    "box",
    "rows",
    "cols",
    "box_nickname",
    "notes",
]
DATE_FORMAT = "%m/%d/%y %H:%M"
VALID_STUDY_ROLES = {"current", "retired"}
SAMPLE_ENTRY_ROWS = 500
BOX_ENTRY_ROWS = 500
PATH_SEPARATOR = " > "
SAMPLE_HEADER_COMMENT_SIZES = {
    "sample_id": (190, 70),
    "sample_type": (220, 70),
    "study": (250, 85),
    "visit": (470, 95),
    "timepoint": (560, 110),
    "aliquot": (300, 85),
    "hemolysis": (360, 85),
    "study_role": (260, 70),
    "volume": (360, 85),
    "volume_units": (340, 70),
    "thaw_count": (470, 85),
    "notes": (220, 70),
    "collection_at": (230, 85),
    "box": (350, 70),
    "position": (540, 85),
}
SAMPLE_TEMPLATE_WIDTHS = {
    "A": 11.265625,
    "B": 12.0,
    "C": 7.86328125,
    "D": 5.59765625,
    "E": 9.265625,
    "F": 7.1328125,
    "G": 10.5,
    "H": 12.06640625,
    "I": 8.796875,
    "J": 12.53125,
    "K": 11.19921875,
    "L": 10.53125,
    "M": 14.0,
    "N": 10.19921875,
    "O": 9.73046875,
}
SAMPLE_CENTERED_ENTRY_COLUMNS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "M", "N", "O"]
SAMPLE_HEADER_COMMENTS = {
    "sample_id": "Required.\nThe participant ID.\nThis may repeat across samples when type, visit, timepoint, or aliquot differ.\nExample: IAS028",
    "sample_type": "Required.\nThe sample type.\nExample: Plasma, Serum, etc.",
    "study": "Optional.\nThe configured study name for the sample.\nExample: IAS, NRS, etc.",
    "visit": "Optional.\nThe visit number. Numbers only.\nUsually only used when the timepoint is reused across multiple visits.\nExample: 1, 2, ...",
    "timepoint": "Optional.\nThe collection timepoint. Numbers only.\nThis can distinguish visits or multiple collections within one visit, such as an OGTT.\nExample: 1, 2, 00, 15, 60, etc.",
    "aliquot": "Optional.\nThe sample aliquot number. Whole numbers only.\nExample: 1, 2, ...",
    "hemolysis": "Optional.\nHemolysis Classification # on a 0 to 6 scale. Whole numbers only.",
    "study_role": "Optional.\nAllowed values: current, retired. Defaults to current.",
    "volume": "Optional.\nCurrent remaining volume in the tube. Number input only.\nExample: 1.2, 3.00, etc.",
    "volume_units": "Optional.\nAllowed values are mL or uL. Defaults to mL if blank.",
    "thaw_count": "Optional.\nNumber of times the sample has been thawed. Whole numbers only. Defaults to 0 if blank.",
    "notes": "Optional.\nFree text notes about the sample.",
    "collection_at": f"Required.\nFormat: {DATE_FORMAT}.\nExample: 03/15/26 14:30",
    "box": "Optional.\nExact box name. Must match an existing unique box name.",
    "position": "Optional.\nPosition label inside the selected box, such as A1. Leave blank for sequential fill into the next empty slot.",
}
BOX_HEADER_COMMENT_SIZES = {
    "parent": (430, 110),
    "box": (260, 80),
    "rows": (260, 80),
    "cols": (260, 80),
    "box_nickname": (300, 80),
    "notes": (260, 80),
}
BOX_TEMPLATE_WIDTHS = {
    "A": 32.0,
    "B": 18.0,
    "C": 8.0,
    "D": 8.0,
    "E": 18.0,
    "F": 28.0,
}
BOX_CENTERED_ENTRY_COLUMNS = ["A", "B", "C", "D"]
BOX_HEADER_COMMENTS = {
    "parent": "Required.\nChoose an existing shelf or rack path from the dropdown.\nExamples: Freezer A > Shelf 1 or Freezer A > Shelf 1 > Rack 2",
    "box": "Required.\nThe new unique box name to create.",
    "rows": "Required.\nNumber of box rows. Whole numbers only and must be greater than zero.",
    "cols": "Required.\nNumber of box columns. Whole numbers only and must be greater than zero.",
    "box_nickname": "Optional.\nSecondary display label for the box, shown in parentheses after the true name.",
    "notes": "Optional.\nFree text notes to store on the box.",
}


class BulkImportError(Exception):
    pass


@dataclass
class ParsedTable:
    headers: list[str]
    rows: list[dict[str, str | None]]
    global_errors: list[str]


@dataclass
class PositionPlan:
    box_id: int
    box_name: str
    box_lookup_names: set[str]
    positions_by_label: dict[str, models.StoragePosition]
    occupied_labels: set[str]


def sample_template_csv() -> str:
    return ",".join(SAMPLE_HEADERS) + "\n"


def sample_template_xlsx(
    sample_types: list[str] | None = None,
    studies: list[str] | None = None,
    boxes: list[str] | None = None,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sample Import"
    sheet.freeze_panes = "A2"

    header_fill = PatternFill(fill_type="solid", fgColor="1F5C4B")
    header_font = Font(color="FFFFFF", bold=True)
    header_alignment = Alignment(horizontal="center", vertical="center")
    centered_entry_alignment = Alignment(horizontal="center", vertical="center")
    notes_entry_alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

    for index, header in enumerate(SAMPLE_HEADERS, start=1):
        cell = sheet.cell(row=1, column=index, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.comment = Comment(SAMPLE_HEADER_COMMENTS.get(header, ""), "Sample Storage")
        cell.comment.width, cell.comment.height = SAMPLE_HEADER_COMMENT_SIZES.get(header, (240, 80))
        sheet.column_dimensions[cell.column_letter].width = SAMPLE_TEMPLATE_WIDTHS.get(cell.column_letter, 16)

    for row_index in range(2, SAMPLE_ENTRY_ROWS + 1):
        for column_letter in SAMPLE_CENTERED_ENTRY_COLUMNS:
            sheet[f"{column_letter}{row_index}"].alignment = centered_entry_alignment
        sheet[f"L{row_index}"].alignment = notes_entry_alignment

    study_role_validation = DataValidation(
        type="list",
        formula1='"current,retired"',
        allow_blank=True,
    )
    study_role_validation.error = "Use current or retired."
    sheet.add_data_validation(study_role_validation)
    study_role_validation.add("H2:H500")

    volume_units_validation = DataValidation(
        type="list",
        formula1='"mL,uL"',
        allow_blank=True,
    )
    volume_units_validation.error = "Use mL or uL."
    sheet.add_data_validation(volume_units_validation)
    volume_units_validation.add("J2:J500")

    lookup_sheet = workbook.create_sheet("_lists")
    lookup_sheet.sheet_state = "hidden"

    sample_types = [value for value in (sample_types or []) if value]
    studies = [value for value in (studies or []) if value]
    boxes = [value for value in (boxes or []) if value]

    lookup_sheet["A1"] = "sample_types"
    for index, value in enumerate(sample_types, start=2):
        lookup_sheet.cell(row=index, column=1, value=value)

    lookup_sheet["B1"] = "studies"
    for index, value in enumerate(studies, start=2):
        lookup_sheet.cell(row=index, column=2, value=value)

    lookup_sheet["C1"] = "boxes"
    for index, value in enumerate(boxes, start=2):
        lookup_sheet.cell(row=index, column=3, value=value)

    if sample_types:
        sample_type_formula = f"'_lists'!$A$2:$A${len(sample_types) + 1}"
        sample_type_validation = DataValidation(type="list", formula1=sample_type_formula, allow_blank=False)
        sample_type_validation.error = "Choose a sample type from the configured list."
        sheet.add_data_validation(sample_type_validation)
        sample_type_validation.add(f"B2:B{SAMPLE_ENTRY_ROWS}")

    if studies:
        study_formula = f"'_lists'!$B$2:$B${len(studies) + 1}"
        study_validation = DataValidation(type="list", formula1=study_formula, allow_blank=True)
        study_validation.error = "Choose a study from the configured list."
        sheet.add_data_validation(study_validation)
        study_validation.add(f"C2:C{SAMPLE_ENTRY_ROWS}")

    if boxes:
        box_formula = f"'_lists'!$C$2:$C${len(boxes) + 1}"
        box_validation = DataValidation(type="list", formula1=box_formula, allow_blank=True)
        box_validation.error = "Choose a box from the configured list."
        sheet.add_data_validation(box_validation)
        box_validation.add(f"N2:N{SAMPLE_ENTRY_ROWS}")

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def workbook_to_csv(file_bytes: bytes) -> str:
    workbook = load_workbook(filename=BytesIO(file_bytes), data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return ""

    max_col = 0
    for row in rows:
        for index, value in enumerate(row, start=1):
            if value not in (None, ""):
                max_col = max(max_col, index)
    if max_col == 0:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)
    for row in rows:
        cleaned_row = [_xlsx_value_to_text(value) for value in row[:max_col]]
        if not any(cell for cell in cleaned_row):
            continue
        writer.writerow(cleaned_row)
    return output.getvalue()


def sample_workbook_to_csv(file_bytes: bytes) -> str:
    return workbook_to_csv(file_bytes)


def box_template_csv() -> str:
    return ",".join(BOX_HEADERS) + "\n"


def box_template_xlsx(
    parent_paths: list[str] | None = None,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Box Import"
    sheet.freeze_panes = "A2"

    header_fill = PatternFill(fill_type="solid", fgColor="1F5C4B")
    header_font = Font(color="FFFFFF", bold=True)
    header_alignment = Alignment(horizontal="center", vertical="center")
    centered_entry_alignment = Alignment(horizontal="center", vertical="center")
    notes_entry_alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

    for index, header in enumerate(BOX_HEADERS, start=1):
        cell = sheet.cell(row=1, column=index, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.comment = Comment(BOX_HEADER_COMMENTS.get(header, ""), "Sample Storage")
        cell.comment.width, cell.comment.height = BOX_HEADER_COMMENT_SIZES.get(header, (260, 80))
        sheet.column_dimensions[cell.column_letter].width = BOX_TEMPLATE_WIDTHS.get(cell.column_letter, 18)

    for row_index in range(2, BOX_ENTRY_ROWS + 1):
        for column_letter in BOX_CENTERED_ENTRY_COLUMNS:
            sheet[f"{column_letter}{row_index}"].alignment = centered_entry_alignment
        for column_letter in ("E", "F"):
            sheet[f"{column_letter}{row_index}"].alignment = notes_entry_alignment

    lookup_sheet = workbook.create_sheet("_lists")
    lookup_sheet.sheet_state = "hidden"

    parent_paths = [value for value in (parent_paths or []) if value]

    lookup_sheet["A1"] = "parent_paths"
    for index, value in enumerate(parent_paths, start=2):
        lookup_sheet.cell(row=index, column=1, value=value)

    if parent_paths:
        parent_formula = f"'_lists'!$A$2:$A${len(parent_paths) + 1}"
        parent_validation = DataValidation(type="list", formula1=parent_formula, allow_blank=False)
        parent_validation.error = "Choose an existing shelf or rack path from the configured list."
        sheet.add_data_validation(parent_validation)
        parent_validation.add(f"A2:A{BOX_ENTRY_ROWS}")

    for column_letter in ("C", "D"):
        dimension_validation = DataValidation(
            type="whole",
            operator="greaterThanOrEqual",
            formula1="1",
            allow_blank=False,
        )
        dimension_validation.error = "Use a whole number greater than or equal to 1."
        sheet.add_data_validation(dimension_validation)
        dimension_validation.add(f"{column_letter}2:{column_letter}{BOX_ENTRY_ROWS}")

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def box_workbook_to_csv(file_bytes: bytes) -> str:
    return workbook_to_csv(file_bytes)


def preview_sample_import(db: Session, raw_payload: str, target_box_id: int | None = None) -> BulkSampleImportPreview:
    table = _parse_table(raw_payload, SAMPLE_HEADERS, {"sample_id"})
    preview = BulkSampleImportPreview(
        raw_payload=raw_payload,
        headers=table.headers,
        target_box_id=target_box_id,
        global_errors=list(table.global_errors),
    )

    sample_type_map = {sample_type.name.lower(): sample_type for sample_type in sample_repository.list_sample_types(db)}
    study_map = _study_lookup_map(sample_repository.list_studies(db))
    existing_sample_identity_keys = sample_repository.list_sample_identity_keys(db)
    box_plan_lookup = _build_box_plan_lookup(db, target_box_id, preview.global_errors)

    preview.rows = [
        BulkSampleImportRow(
            row_number=index + 2,
            sample_id=row.get("sample_id"),
            sample_type=row.get("sample_type"),
            study=row.get("study"),
            visit=row.get("visit"),
            timepoint=row.get("timepoint"),
            aliquot=row.get("aliquot"),
            hemolysis=row.get("hemolysis"),
            study_role=row.get("study_role"),
            volume=row.get("volume"),
            volume_units=row.get("volume_units"),
            thaw_count=row.get("thaw_count"),
            notes=row.get("notes"),
            collection_at=row.get("collection_at"),
            box=row.get("box"),
            position=row.get("position"),
        )
        for index, row in enumerate(table.rows)
    ]
    duplicate_identities_in_file = _duplicate_sample_row_identities(preview.rows, sample_type_map)

    if preview.global_errors:
        for row in preview.rows:
            row.errors.extend(preview.global_errors)
            row.status = "invalid"
        _finalize_preview_counts(preview)
        return preview

    explicit_positions_by_box: dict[int, set[str]] = {}
    valid_without_position_by_box: dict[int, list[BulkSampleImportRow]] = {}
    for row in preview.rows:
        _validate_sample_row(
            row,
            sample_type_map=sample_type_map,
            study_map=study_map,
            existing_sample_identity_keys=existing_sample_identity_keys,
            duplicate_identities_in_file=duplicate_identities_in_file,
            box_plan_lookup=box_plan_lookup,
            explicit_positions_by_box=explicit_positions_by_box,
            default_target_box_id=target_box_id,
        )
        resolved_plan = _resolve_plan_for_row(box_plan_lookup, row.box, target_box_id)
        if row.valid and resolved_plan is not None and not row.position:
            valid_without_position_by_box.setdefault(resolved_plan.box_id, []).append(row)

    for box_id, valid_without_position in valid_without_position_by_box.items():
        position_plan = box_plan_lookup.get(box_id)
        if position_plan is None:
            continue
        available_labels = [
            label
            for label, position in sorted(position_plan.positions_by_label.items(), key=lambda item: (item[1].row, item[1].col))
            if label not in position_plan.occupied_labels and label not in explicit_positions_by_box.get(box_id, set())
        ]
        for row in valid_without_position:
            if not available_labels:
                row.errors.append("No open positions remain for sequential fill")
                row.valid = False
                row.status = "invalid"
                continue
            row.assigned_box_name = position_plan.box_name
            row.assigned_position = available_labels.pop(0)
            row.status = "valid"
    _finalize_preview_counts(preview)
    return preview


def commit_sample_import(
    db: Session,
    data: BulkSampleImportCommitInput,
    user: models.User | None,
) -> BulkSampleImportCommitResult:
    preview = preview_sample_import(db, data.raw_payload, data.target_box_id)
    result = BulkSampleImportCommitResult(target_box_id=data.target_box_id, global_errors=list(preview.global_errors))
    if preview.global_errors:
        result.rows = [row.model_copy(update={"status": "skipped"}) for row in preview.rows]
        result.skipped_rows = len(result.rows)
        return result

    box_plan_lookup = _build_box_plan_lookup(db, data.target_box_id, [])
    box_name_lookup = {plan.box_name.lower(): plan for plan in box_plan_lookup.values()}
    sample_type_map = {sample_type.name.lower(): sample_type for sample_type in sample_repository.list_sample_types(db)}
    study_map = _study_lookup_map(sample_repository.list_studies(db))

    for row in preview.rows:
        row_copy = row.model_copy(deep=True)
        if not row.valid:
            row_copy.status = "skipped"
            result.rows.append(row_copy)
            result.skipped_rows += 1
            continue
        try:
            create_input = SampleCreateInput(
                sample_id=row.sample_id or "",
                sample_type_id=sample_type_map[row.sample_type.lower()].id if row.sample_type else None,
                study_id=study_map[row.study.lower()].id if row.study else None,
                visit_label=row.visit,
                timepoint_label=row.timepoint,
                aliquot_number=_parse_int(row.aliquot),
                hemolysis_classification=_parse_int(row.hemolysis),
                study_role=(row.study_role or "current"),
                volume=_parse_float(row.volume),
                volume_units=row.volume_units or "mL",
                thaw_count=_parse_int(row.thaw_count) or 0,
                notes=row.notes,
                collection_at=_parse_datetime(row.collection_at),
            )
            sample = sample_service.create_sample(db, create_input, user, commit=False)
            if row.assigned_box_name and row.assigned_position:
                position_plan = box_name_lookup.get(row.assigned_box_name.lower())
                if position_plan is None:
                    raise BulkImportError("Assigned box was not found during import")
                position_id = position_plan.positions_by_label[row.assigned_position].id
                sample_service.place_sample(db, sample.id, PlaceSampleInput(position_id=position_id), user, commit=False)
            db.commit()
            row_copy.status = "imported"
            result.rows.append(row_copy)
            result.imported_rows += 1
        except Exception as exc:
            db.rollback()
            row_copy.status = "failed"
            row_copy.errors.append(str(exc))
            result.rows.append(row_copy)
            result.failed_rows += 1
    return result


def preview_box_import(db: Session, raw_payload: str) -> BulkBoxImportPreview:
    table = _parse_table(raw_payload, BOX_HEADERS, {"parent", "box", "rows", "cols"})
    preview = BulkBoxImportPreview(raw_payload=raw_payload, headers=table.headers, global_errors=list(table.global_errors))
    all_nodes = storage_service.list_all_nodes(db)
    parent_lookup = _box_parent_lookup(all_nodes)
    preview.rows = [
        BulkBoxImportRow(
            row_number=index + 2,
            parent=row.get("parent"),
            box=row.get("box"),
            rows=row.get("rows"),
            cols=row.get("cols"),
            box_nickname=row.get("box_nickname"),
            notes=row.get("notes"),
        )
        for index, row in enumerate(table.rows)
    ]
    if preview.global_errors:
        for row in preview.rows:
            row.errors.extend(preview.global_errors)
        _finalize_box_counts(preview)
        return preview

    box_duplicates = _duplicate_keys(table.rows, "box")
    box_name_conflicts = _existing_box_names(all_nodes)

    for row in preview.rows:
        _validate_box_row(
            row,
            parent_lookup=parent_lookup,
            box_duplicates=box_duplicates,
            existing_box_names=box_name_conflicts,
        )
    _finalize_box_counts(preview)
    return preview


def commit_box_import(
    db: Session,
    data: BulkBoxImportCommitInput,
    user: models.User | None,
) -> BulkBoxImportCommitResult:
    preview = preview_box_import(db, data.raw_payload)
    result = BulkBoxImportCommitResult(global_errors=list(preview.global_errors))
    if preview.global_errors:
        result.rows = [row.model_copy(update={"status": "skipped"}) for row in preview.rows]
        result.skipped_rows = len(result.rows)
        return result

    for row in preview.rows:
        row_copy = row.model_copy(deep=True)
        if not row.valid:
            row_copy.status = "skipped"
            result.rows.append(row_copy)
            result.skipped_rows += 1
            continue
        try:
            all_nodes = storage_service.list_all_nodes(db)
            parent = _resolve_box_parent(all_nodes, row.parent)
            if parent is None:
                raise BulkImportError("Storage path no longer exists")
            box = storage_service.create_storage_node(
                db,
                StorageNodeCreate(
                    name=row.box or "",
                    nickname=row.box_nickname,
                    notes=row.notes,
                    node_type="box",
                    parent_id=parent.id,
                ),
                user,
                commit=False,
            )
            storage_service.create_box_positions(
                db,
                BoxCreateInput(box_id=box.id, rows=_parse_int(row.rows) or 0, cols=_parse_int(row.cols) or 0),
                user,
                commit=False,
            )
            db.commit()
            row_copy.status = "imported"
            result.rows.append(row_copy)
            result.imported_rows += 1
        except Exception as exc:
            db.rollback()
            row_copy.status = "failed"
            row_copy.errors.append(str(exc))
            result.rows.append(row_copy)
            result.failed_rows += 1
    return result


def _parse_table(raw_payload: str, allowed_headers: list[str], required_headers: set[str]) -> ParsedTable:
    payload = (raw_payload or "").replace("\ufeff", "").strip()
    if not payload:
        return ParsedTable(headers=[], rows=[], global_errors=["No import data provided"])
    first_line = payload.splitlines()[0] if payload.splitlines() else ""
    delimiter = "\t" if "\t" in first_line else ","
    reader = csv.DictReader(io.StringIO(payload), delimiter=delimiter)
    headers = [header.strip() for header in (reader.fieldnames or []) if header and header.strip()]
    global_errors: list[str] = []
    missing_headers = sorted(required_headers.difference(headers))
    unknown_headers = sorted(set(headers).difference(allowed_headers))
    if missing_headers:
        global_errors.append(f"Missing required columns: {', '.join(missing_headers)}")
    if unknown_headers:
        global_errors.append(f"Unknown columns: {', '.join(unknown_headers)}")
    rows: list[dict[str, str | None]] = []
    for row in reader:
        cleaned = {key.strip(): _clean_value(value) for key, value in row.items() if key is not None}
        if not any(value for value in cleaned.values()):
            continue
        rows.append(cleaned)
    return ParsedTable(headers=headers, rows=rows, global_errors=global_errors)


def _validate_sample_row(
    row: BulkSampleImportRow,
    *,
    sample_type_map: dict[str, models.SampleType],
    study_map: dict[str, models.Study],
    existing_sample_identity_keys: set[tuple[str, int | None, str | None, str | None, int | None]],
    duplicate_identities_in_file: set[tuple[str, int | None, str | None, str | None, int | None]],
    box_plan_lookup: dict[int, PositionPlan],
    explicit_positions_by_box: dict[int, set[str]],
    default_target_box_id: int | None,
) -> None:
    sample_id = (row.sample_id or "").strip()
    if not sample_id:
        row.errors.append("Sample ID is required")

    if not row.sample_type:
        row.errors.append("Sample type is required")
    elif row.sample_type.lower() not in sample_type_map:
        row.errors.append("Sample type was not found")
    if row.study and row.study.lower() not in study_map:
        row.errors.append("Study was not found")
    if row.visit and not str(row.visit).strip().isdigit():
        row.errors.append("Visit must contain numbers only")
    if row.timepoint and not str(row.timepoint).strip().isdigit():
        row.errors.append("Timepoint must contain numbers only")
    if row.study_role and row.study_role not in VALID_STUDY_ROLES:
        row.errors.append("Study role must be current or retired")
    if row.aliquot and _parse_int(row.aliquot) is None:
        row.errors.append("Aliquot must be a whole number")
    if row.hemolysis and (_parse_int(row.hemolysis) is None or not 0 <= (_parse_int(row.hemolysis) or 0) <= 6):
        row.errors.append("Hemolysis must be a whole number from 0 to 6")
    if row.thaw_count and (_parse_int(row.thaw_count) is None or (_parse_int(row.thaw_count) or 0) < 0):
        row.errors.append("Thaw count must be zero or greater")
    if row.volume and (_parse_float(row.volume) is None or (_parse_float(row.volume) or 0) < 0):
        row.errors.append("Volume must be zero or greater")
    if row.volume_units and row.volume_units not in {"mL", "uL"}:
        row.errors.append("Volume units must be mL or uL")
    if not row.collection_at:
        row.errors.append("Collection date is required")
    elif _parse_datetime(row.collection_at) is None:
        row.errors.append(f"Collection date must use {DATE_FORMAT}")

    sample_type = sample_type_map.get((row.sample_type or "").lower()) if row.sample_type else None
    identity_key = None
    if sample_id and sample_type is not None:
        identity_key = sample_repository.build_identity_key(
            sample_id,
            sample_type.id,
            row.visit,
            row.timepoint,
            _parse_int(row.aliquot),
        )
        if identity_key in existing_sample_identity_keys:
            row.errors.append("This ID, type, visit, timepoint, and aliquot combination already exists")
        elif identity_key in duplicate_identities_in_file:
            row.errors.append("This ID, type, visit, timepoint, and aliquot combination is duplicated in this import")

    position_plan = _resolve_plan_for_row(box_plan_lookup, row.box, default_target_box_id)
    if row.box and position_plan is None:
        row.errors.append("Box was not found")
    elif position_plan is not None:
        row.assigned_box_name = position_plan.box_name

    if row.position:
        if position_plan is None:
            row.errors.append("Position can only be used when a box is resolved")
        else:
            label = row.position.upper()
            explicit_positions = explicit_positions_by_box.setdefault(position_plan.box_id, set())
            if label not in position_plan.positions_by_label:
                row.errors.append("Position does not exist in the resolved box")
            elif label in position_plan.occupied_labels:
                row.errors.append("Position is already occupied")
            elif label in explicit_positions:
                row.errors.append("Position is duplicated in this import for the same box")
            else:
                row.assigned_box_name = position_plan.box_name
                row.assigned_position = label
                explicit_positions.add(label)

    row.valid = not row.errors
    row.status = "valid" if row.valid else "invalid"


def _build_box_plan_lookup(db: Session, target_box_id: int | None, global_errors: list[str]) -> dict[int, PositionPlan]:
    plans: dict[int, PositionPlan] = {}
    for box in storage_service.list_boxes(db):
        plan = _build_position_plan_for_box(db, box)
        if plan is not None:
            plans[box.id] = plan
    if target_box_id is not None and target_box_id not in plans:
        global_errors.append("Selected target box was not found")
    return plans


def _build_position_plan_for_box(db: Session, box_node: models.StorageNode) -> PositionPlan | None:
    box = storage_service.get_box_view(db, box_node.id)
    if box is None:
        return None
    position_map = {position.label.upper(): storage_service.get_position(db, position.id) for position in box.positions}
    if any(position is None for position in position_map.values()):
        return None
    positions = {label: position for label, position in position_map.items() if position is not None}
    occupied = {label for label, position in positions.items() if position.location is not None}
    lookup_names = {box.box_name.lower(), box_node.name.lower()}
    return PositionPlan(
        box_id=box.box_id,
        box_name=box.box_name,
        box_lookup_names=lookup_names,
        positions_by_label=positions,
        occupied_labels=occupied,
    )


def _validate_box_row(
    row: BulkBoxImportRow,
    *,
    parent_lookup: dict[str, models.StorageNode],
    box_duplicates: set[str],
    existing_box_names: set[str],
) -> None:
    row.parent = _clean_value(row.parent)
    parent = row.parent or ""
    box = (row.box or "").strip()
    if not parent:
        row.errors.append("Parent path is required")
    elif parent not in parent_lookup:
        row.errors.append("Parent path was not found")
    if not box:
        row.errors.append("Box is required")
    parsed_rows = _parse_int(row.rows)
    parsed_cols = _parse_int(row.cols)
    if row.rows is None or parsed_rows is None or parsed_rows <= 0:
        row.errors.append("Rows must be a positive whole number")
    if row.cols is None or parsed_cols is None or parsed_cols <= 0:
        row.errors.append("Cols must be a positive whole number")
    if box and box.lower() in box_duplicates:
        row.errors.append("Box name is duplicated in this import")
    if box and box in existing_box_names:
        row.errors.append("Box name already exists")

    row.valid = not row.errors
    row.status = "valid" if row.valid else "invalid"


def _box_parent_lookup(all_nodes: list[models.StorageNode]) -> dict[str, models.StorageNode]:
    return {
        PATH_SEPARATOR.join(node.path_names()): node
        for node in all_nodes
        if node.node_type in {models.StorageNodeType.shelf, models.StorageNodeType.rack}
    }


def _resolve_box_parent(all_nodes: list[models.StorageNode], parent_path: str | None) -> models.StorageNode | None:
    if not parent_path:
        return None
    return _box_parent_lookup(all_nodes).get(parent_path)


def _duplicate_keys(rows: list[dict[str, str | None]], key: str) -> set[str]:
    counts: dict[str, int] = {}
    for row in rows:
        value = (row.get(key) or "").strip().lower()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return {value for value, count in counts.items() if count > 1}


def _duplicate_sample_row_identities(
    rows: list[BulkSampleImportRow],
    sample_type_map: dict[str, models.SampleType],
) -> set[tuple[str, int | None, str | None, str | None, int | None]]:
    counts: dict[tuple[str, int | None, str | None, str | None, int | None], int] = {}
    for row in rows:
        sample_id = (row.sample_id or "").strip()
        sample_type = sample_type_map.get((row.sample_type or "").lower()) if row.sample_type else None
        if not sample_id or sample_type is None:
            continue
        identity_key = sample_repository.build_identity_key(
            sample_id,
            sample_type.id,
            row.visit,
            row.timepoint,
            _parse_int(row.aliquot),
        )
        counts[identity_key] = counts.get(identity_key, 0) + 1
    return {identity_key for identity_key, count in counts.items() if count > 1}


def _existing_box_names(all_nodes: list[models.StorageNode]) -> set[str]:
    return {node.name for node in all_nodes if node.node_type == models.StorageNodeType.box}


def _study_lookup_map(studies: list[models.Study]) -> dict[str, models.Study]:
    lookup: dict[str, models.Study] = {}
    for study in studies:
        lookup[study.name.lower()] = study
    return lookup


def _resolve_plan_for_row(
    box_plan_lookup: dict[int, PositionPlan],
    row_box: str | None,
    default_target_box_id: int | None,
) -> PositionPlan | None:
    if row_box:
        normalized = row_box.strip().lower()
        for plan in box_plan_lookup.values():
            if normalized in plan.box_lookup_names:
                return plan
        return None
    if default_target_box_id is not None:
        return box_plan_lookup.get(default_target_box_id)
    return None


def _finalize_preview_counts(preview: BulkSampleImportPreview) -> None:
    preview.total_rows = len(preview.rows)
    preview.valid_rows = sum(1 for row in preview.rows if row.valid)
    preview.invalid_rows = preview.total_rows - preview.valid_rows


def _finalize_box_counts(preview: BulkBoxImportPreview) -> None:
    preview.total_rows = len(preview.rows)
    preview.valid_rows = sum(1 for row in preview.rows if row.valid)
    preview.invalid_rows = preview.total_rows - preview.valid_rows


def _parse_int(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    try:
        return datetime.strptime(str(value).strip(), DATE_FORMAT)
    except ValueError:
        return None


def _clean_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _xlsx_value_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()
