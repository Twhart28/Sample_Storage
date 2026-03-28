from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domain import models
from app.schemas import SampleSearchQuery

_SAMPLE_OPTIONS = (
    joinedload(models.Sample.sample_type),
    joinedload(models.Sample.study),
    selectinload(models.Sample.location)
    .joinedload(models.SampleLocation.position)
    .joinedload(models.StoragePosition.box),
    selectinload(models.Sample.note_entries).joinedload(models.SampleNoteEntry.user),
)


def get_by_id(db: Session, sample_id: int) -> models.Sample | None:
    stmt = select(models.Sample).where(models.Sample.id == sample_id).options(*_SAMPLE_OPTIONS)
    return db.execute(stmt).unique().scalar_one_or_none()


def get_by_ids(db: Session, sample_ids: list[int]) -> list[models.Sample]:
    if not sample_ids:
        return []
    stmt = select(models.Sample).where(models.Sample.id.in_(sample_ids)).options(*_SAMPLE_OPTIONS)
    rows = list(db.execute(stmt).unique().scalars().all())
    sample_map = {sample.id: sample for sample in rows}
    return [sample_map[sample_id] for sample_id in sample_ids if sample_id in sample_map]


def get_by_identifier(db: Session, sample_identifier: str) -> models.Sample | None:
    stmt = (
        select(models.Sample)
        .where(models.Sample.sample_id == sample_identifier)
        .options(*_SAMPLE_OPTIONS)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def get_by_identity(
    db: Session,
    sample_identifier: str,
    sample_type_id: int | None,
    visit_label: str | None,
    timepoint_label: str | None,
    aliquot_number: int | None,
    *,
    exclude_sample_pk: int | None = None,
) -> models.Sample | None:
    stmt = select(models.Sample).options(*_SAMPLE_OPTIONS).where(func.lower(models.Sample.sample_id) == sample_identifier.lower())
    if sample_type_id is None:
        stmt = stmt.where(models.Sample.sample_type_id.is_(None))
    else:
        stmt = stmt.where(models.Sample.sample_type_id == sample_type_id)
    stmt = stmt.where(_optional_text_match(models.Sample.visit_label, visit_label))
    stmt = stmt.where(_optional_text_match(models.Sample.timepoint_label, timepoint_label))
    if aliquot_number is None:
        stmt = stmt.where(models.Sample.aliquot_number.is_(None))
    else:
        stmt = stmt.where(models.Sample.aliquot_number == aliquot_number)
    if exclude_sample_pk is not None:
        stmt = stmt.where(models.Sample.id != exclude_sample_pk)
    return db.execute(stmt).unique().scalar_one_or_none()


def list_sample_identifiers(db: Session) -> list[str]:
    stmt = select(models.Sample.sample_id)
    return [row[0] for row in db.execute(stmt).all()]


def list_sample_identity_keys(db: Session) -> set[tuple[str, int | None, str | None, str | None, int | None]]:
    stmt = select(
        models.Sample.sample_id,
        models.Sample.sample_type_id,
        models.Sample.visit_label,
        models.Sample.timepoint_label,
        models.Sample.aliquot_number,
    )
    return {
        build_identity_key(sample_id, sample_type_id, visit_label, timepoint_label, aliquot_number)
        for sample_id, sample_type_id, visit_label, timepoint_label, aliquot_number in db.execute(stmt).all()
    }


def search(db: Session, filters: SampleSearchQuery) -> list[models.Sample]:
    stmt = select(models.Sample).options(*_SAMPLE_OPTIONS)
    if filters.sort == "study":
        stmt = stmt.outerjoin(models.Sample.study)
    elif filters.sort == "sample_type":
        stmt = stmt.outerjoin(models.Sample.sample_type)
    elif filters.sort == "location":
        stmt = stmt.outerjoin(models.Sample.location).outerjoin(models.SampleLocation.position)

    if filters.q:
        like = f"%{filters.q}%"
        stmt = stmt.where(
            or_(
                models.Sample.sample_id.ilike(like),
                models.Sample.notes.ilike(like),
                models.Sample.sample_type.has(models.SampleType.name.ilike(like)),
                models.Sample.visit_label.ilike(like),
                models.Sample.timepoint_label.ilike(like),
                models.Sample.study.has(models.Study.name.ilike(like)),
                models.Sample.location.has(
                    models.SampleLocation.position.has(
                        or_(
                            models.StoragePosition.label.ilike(like),
                            models.StoragePosition.box.has(models.StorageNode.name.ilike(like)),
                        )
                    )
                ),
            )
        )
    sample_type_ids = _merged_values(filters.sample_type_ids, filters.sample_type_id)
    if sample_type_ids:
        stmt = stmt.where(models.Sample.sample_type_id.in_(sample_type_ids))
    study_ids = _merged_values(filters.study_ids, filters.study_id)
    if study_ids:
        stmt = stmt.where(models.Sample.study_id.in_(study_ids))
    study_roles = _merged_values(filters.study_roles, filters.study_role)
    if study_roles:
        stmt = stmt.where(models.Sample.study_role.in_(study_roles))
    custodies = _merged_values(filters.custodies, filters.custody)
    if custodies:
        custody_conditions = []
        for custody in custodies:
            if custody == "archived":
                custody_conditions.append(models.Sample.is_archived.is_(True))
            elif custody == "out_for_analysis":
                custody_conditions.append(models.Sample.is_out_for_analysis.is_(True))
            elif custody == "in_storage":
                custody_conditions.append(
                    and_(
                        models.Sample.is_archived.is_(False),
                        models.Sample.is_out_for_analysis.is_(False),
                        models.Sample.location.has(),
                    )
                )
            elif custody == "unplaced":
                custody_conditions.append(
                    and_(
                        models.Sample.is_archived.is_(False),
                        models.Sample.is_out_for_analysis.is_(False),
                        ~models.Sample.location.has(),
                    )
                )
        if custody_conditions:
            stmt = stmt.where(or_(*custody_conditions))
    usages = _merged_values(filters.usages, filters.usage)
    if usages:
        usage_conditions = []
        for usage in usages:
            if usage == "used":
                usage_conditions.append(models.Sample.thaw_count > 0)
            elif usage == "unused":
                usage_conditions.append(models.Sample.thaw_count <= 0)
        if usage_conditions:
            stmt = stmt.where(or_(*usage_conditions))
    if filters.location_state == "placed":
        stmt = stmt.where(models.Sample.location.has())
    elif filters.location_state == "unplaced":
        stmt = stmt.where(~models.Sample.location.has())
    if filters.storage_node_ids:
        matching_box_ids = _matching_box_ids_for_storage_nodes(db, filters.storage_node_ids)
        if not matching_box_ids:
            stmt = stmt.where(false())
        else:
            stmt = stmt.where(
                models.Sample.location.has(
                    models.SampleLocation.position.has(
                        models.StoragePosition.box_id.in_(matching_box_ids)
                    )
                )
            )
    visit_labels = _merged_values(filters.visit_labels, filters.visit_label)
    if visit_labels:
        stmt = stmt.where(models.Sample.visit_label.in_(visit_labels))
    timepoint_labels = _merged_values(filters.timepoint_labels, filters.timepoint_label)
    if timepoint_labels:
        stmt = stmt.where(models.Sample.timepoint_label.in_(timepoint_labels))
    if filters.aliquot_number is not None:
        stmt = stmt.where(models.Sample.aliquot_number == filters.aliquot_number)
    if filters.aliquot_min is not None:
        stmt = stmt.where(models.Sample.aliquot_number >= filters.aliquot_min)
    if filters.aliquot_max is not None:
        stmt = stmt.where(models.Sample.aliquot_number <= filters.aliquot_max)
    if filters.hemolysis_classification is not None:
        stmt = stmt.where(models.Sample.hemolysis_classification == filters.hemolysis_classification)
    if filters.hemolysis_min is not None:
        stmt = stmt.where(models.Sample.hemolysis_classification >= filters.hemolysis_min)
    if filters.hemolysis_max is not None:
        stmt = stmt.where(models.Sample.hemolysis_classification <= filters.hemolysis_max)
    if filters.thaw_count_min is not None:
        stmt = stmt.where(models.Sample.thaw_count >= filters.thaw_count_min)
    if filters.thaw_count_max is not None:
        stmt = stmt.where(models.Sample.thaw_count <= filters.thaw_count_max)
    if filters.volume_min is not None:
        stmt = stmt.where(models.Sample.volume >= filters.volume_min)
    if filters.volume_max is not None:
        stmt = stmt.where(models.Sample.volume <= filters.volume_max)
    stmt = _apply_datetime_range(stmt, models.Sample.collection_at, filters.collection_from, filters.collection_to)
    stmt = _apply_datetime_range(stmt, models.Sample.created_at, filters.registered_from, filters.registered_to)
    stmt = _apply_datetime_range(stmt, models.Sample.updated_at, filters.updated_from, filters.updated_to)
    if filters.has_notes is True:
        stmt = stmt.where(
            or_(
                and_(models.Sample.notes.is_not(None), models.Sample.notes != ""),
                models.Sample.note_entries.any(),
            )
        )
    elif filters.has_notes is False:
        stmt = stmt.where(
            and_(
                or_(models.Sample.notes.is_(None), models.Sample.notes == ""),
                ~models.Sample.note_entries.any(),
            )
        )

    stmt = stmt.order_by(*_sort_columns(filters))
    return list(db.execute(stmt).unique().scalars().all())


def recent(db: Session, limit: int = 8) -> list[models.Sample]:
    stmt = select(models.Sample).options(*_SAMPLE_OPTIONS).order_by(models.Sample.updated_at.desc()).limit(limit)
    return list(db.execute(stmt).unique().scalars().all())


def list_sample_types(db: Session) -> list[models.SampleType]:
    stmt = select(models.SampleType).order_by(models.SampleType.name.asc())
    return list(db.execute(stmt).scalars().all())


def get_sample_type(db: Session, sample_type_id: int) -> models.SampleType | None:
    return db.get(models.SampleType, sample_type_id)


def count_samples_for_sample_type(db: Session, sample_type_id: int) -> int:
    stmt = select(func.count(models.Sample.id)).where(models.Sample.sample_type_id == sample_type_id)
    return int(db.execute(stmt).scalar_one())


def list_studies(db: Session) -> list[models.Study]:
    stmt = select(models.Study).order_by(models.Study.name.asc())
    return list(db.execute(stmt).scalars().all())


def get_study(db: Session, study_id: int) -> models.Study | None:
    return db.get(models.Study, study_id)


def count_samples_for_study(db: Session, study_id: int) -> int:
    stmt = select(func.count(models.Sample.id)).where(models.Sample.study_id == study_id)
    return int(db.execute(stmt).scalar_one())


def get_study_by_name(db: Session, name: str) -> models.Study | None:
    stmt = select(models.Study).where(models.Study.name == name)
    return db.execute(stmt).scalar_one_or_none()


def _apply_datetime_range(stmt, column, date_from, date_to):
    if date_from is not None:
        stmt = stmt.where(column >= date_from)
    if date_to is not None:
        stmt = stmt.where(column <= date_to)
    return stmt


def _sort_columns(filters: SampleSearchQuery):
    sort_map = {
        "sample_id": models.Sample.sample_id,
        "study": models.Study.name,
        "sample_type": models.SampleType.name,
        "study_role": models.Sample.study_role,
        "custody": case(
            (models.Sample.is_archived.is_(True), 0),
            (models.Sample.is_out_for_analysis.is_(True), 1),
            (models.Sample.location.has(), 2),
            else_=3,
        ),
        "usage": case((models.Sample.thaw_count > 0, 1), else_=0),
        "volume": models.Sample.volume,
        "location": models.StoragePosition.label,
        "visit_label": models.Sample.visit_label,
        "timepoint_label": models.Sample.timepoint_label,
        "aliquot_number": models.Sample.aliquot_number,
        "hemolysis_classification": models.Sample.hemolysis_classification,
        "thaw_count": models.Sample.thaw_count,
        "collection_at": models.Sample.collection_at,
        "created_at": models.Sample.created_at,
        "updated_at": models.Sample.updated_at,
    }
    column = sort_map.get(filters.sort, models.Sample.sample_id)
    if filters.sort_dir == "desc":
        return (column.desc(), models.Sample.sample_id.asc())
    return (column.asc(), models.Sample.sample_id.asc())


def _merged_values(values: list, single):
    merged = list(values or [])
    if single is not None and single not in merged:
        merged.append(single)
    return merged


def build_identity_key(
    sample_identifier: str,
    sample_type_id: int | None,
    visit_label: str | None,
    timepoint_label: str | None,
    aliquot_number: int | None,
) -> tuple[str, int | None, str | None, str | None, int | None]:
    return (
        sample_identifier.strip().lower(),
        sample_type_id,
        _normalize_optional_text(visit_label),
        _normalize_optional_text(timepoint_label),
        aliquot_number,
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _optional_text_match(column, value: str | None):
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return column.is_(None)
    return func.lower(column) == normalized


def _matching_box_ids_for_storage_nodes(db: Session, storage_node_ids: list[int]) -> set[int]:
    stmt = select(models.StorageNode.id, models.StorageNode.parent_id, models.StorageNode.node_type)
    rows = db.execute(stmt).all()
    children_by_parent: dict[int | None, list[tuple[int, models.StorageNodeType]]] = defaultdict(list)
    for node_id, parent_id, node_type in rows:
        children_by_parent[parent_id].append((node_id, node_type))

    box_ids: set[int] = set()
    seen: set[int] = set()
    stack = list(storage_node_ids)
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        for child_id, node_type in children_by_parent.get(node_id, []):
            if child_id not in seen:
                stack.append(child_id)
            if node_type == models.StorageNodeType.box:
                box_ids.add(child_id)

    for node_id, _parent_id, node_type in rows:
        if node_id in storage_node_ids and node_type == models.StorageNodeType.box:
            box_ids.add(node_id)
    return box_ids
