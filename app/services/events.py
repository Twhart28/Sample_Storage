from __future__ import annotations

from datetime import datetime

from app.domain import models
from app.repositories import events as event_repository
from app.schemas import (
    EventChangeItem,
    EventContextItem,
    EventDetailSection,
    EventGroupItem,
    EventSearchQuery,
    EventView,
)
from app.services import storage as storage_service

STORAGE_DISPLAY_ACTIONS = {
    "create_storage",
    "create_box",
    "update_storage",
    "move_storage",
    "delete_storage",
}

DISPLAY_ACTION_LABELS = {
    "create_sample": "Create sample",
    "update_sample": "Update sample",
    "analyze_sample": "Analysis",
    "place_sample": "Place sample",
    "move_sample": "Move sample",
    "delete_sample": "Delete sample",
    "create_storage": "Create storage",
    "create_box": "Create box",
    "update_storage": "Update storage",
    "move_storage": "Move storage",
    "delete_storage": "Delete storage",
    "add_note": "Add note",
}


def build_event_view(event) -> EventView:
    payload = event.payload
    sample_identifier = event.sample.sample_id if event.sample else payload.get("sample_identifier")
    username = event.user.username if event.user else None
    display_action = _display_action(event, payload)
    action_label = DISPLAY_ACTION_LABELS.get(display_action, _labelize(display_action))
    (
        title,
        context_line,
        drawer_context_line,
        pill_items,
        change_items,
        metadata_section,
        detail_sections,
        related_url,
    ) = _format_event(event, payload, sample_identifier, username, display_action)
    risk_level = _risk_level(event, payload, display_action)
    has_legacy_detail_gap = _has_legacy_detail_gap(event, payload, change_items)
    detail_items = [
        EventContextItem(label="Action", value=action_label),
        EventContextItem(label="Recorded", value=event.created_at.strftime("%m/%d/%y %H:%M")),
    ]
    if metadata_section:
        detail_items.extend(metadata_section.items)
    detail_items.extend(item for section in detail_sections for item in section.items)
    summary = f"{action_label}: {title}"
    return EventView(
        id=event.id,
        event_type=event.event_type.value,
        display_action=display_action,
        sample_id=event.sample_id,
        sample_identifier=sample_identifier,
        user_id=event.user_id,
        username=username,
        from_position_id=event.from_position_id,
        to_position_id=event.to_position_id,
        payload=payload,
        raw_payload=payload,
        action_label=action_label,
        summary=summary,
        title=title,
        context_line=context_line,
        drawer_context_line=drawer_context_line,
        subtitle=context_line,
        pill_items=pill_items[:3],
        primary_items=pill_items[:3],
        context_items=pill_items[:3],
        detail_items=detail_items,
        change_items=change_items,
        metadata_section=metadata_section,
        detail_sections=detail_sections,
        risk_level=risk_level,
        is_high_risk=risk_level == "high",
        has_legacy_detail_gap=has_legacy_detail_gap,
        severity=_severity_for_risk(risk_level),
        related_url=related_url,
        created_at=event.created_at,
    )


def list_events(
    db,
    limit: int | None = None,
    sample_id: int | None = None,
    query: EventSearchQuery | None = None,
) -> list[EventView]:
    effective_query = query or EventSearchQuery(limit=limit or 50)
    if limit is not None:
        effective_query = effective_query.model_copy(update={"limit": limit})

    repository_query = effective_query
    if effective_query.event_type in STORAGE_DISPLAY_ACTIONS:
        repository_query = effective_query.model_copy(
            update={
                "event_type": models.EventType.create_storage.value,
                "limit": max(effective_query.limit * 8, effective_query.limit),
            }
        )
    elif effective_query.event_type == "update_sample":
        repository_query = effective_query.model_copy(
            update={
                "event_type": None,
                "limit": max(effective_query.limit * 4, effective_query.limit),
            }
        )
    elif sample_id is None:
        repository_query = effective_query.model_copy(update={"limit": max(effective_query.limit * 4, effective_query.limit)})

    views = [
        build_event_view(event)
        for event in event_repository.list_recent(db, query=repository_query, sample_id=sample_id)
    ]
    if effective_query.event_type:
        views = [event for event in views if event.display_action == effective_query.event_type]
    if sample_id is None:
        views = _group_batch_views(views)
    return views[: effective_query.limit]


def _group_batch_views(views: list[EventView]) -> list[EventView]:
    groups: dict[tuple[str, str], list[EventView]] = {}

    for view in views:
        group_key = _batch_group_key(view)
        if group_key is None:
            continue
        groups.setdefault(group_key, []).append(view)

    expanded: list[EventView] = []
    seen_groups: set[tuple[str, str]] = set()
    for view in views:
        group_key = _batch_group_key(view)
        if group_key is None:
            expanded.append(view)
            continue
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        children = sorted(groups[group_key], key=lambda item: item.created_at, reverse=True)
        expanded.append(_build_group_parent_view(children))
        for child in children:
            expanded.append(
                child.model_copy(
                    update={
                        "is_group_child": True,
                        "group_kind": group_key[0],
                        "group_id": group_key[1],
                        "group_title": str(child.raw_payload.get("batch_group_title") or child.title),
                    }
                )
            )
    return expanded


def list_event_users(db) -> list[dict[str, str | int]]:
    return [
        {"id": user.id, "username": user.username, "label": user.full_name or user.username}
        for user in event_repository.list_users_with_events(db)
    ]


def list_event_types(include_notes: bool = False) -> list[dict[str, str]]:
    values = [
        "create_sample",
        "update_sample",
        "analyze_sample",
        "place_sample",
        "move_sample",
        "delete_sample",
        "create_storage",
        "create_box",
        "update_storage",
        "move_storage",
        "delete_storage",
    ]
    if include_notes:
        values.append("add_note")
    return [{"value": value, "label": DISPLAY_ACTION_LABELS[value]} for value in values]


def _format_event(
    event,
    payload: dict,
    sample_identifier: str | None,
    username: str | None,
    display_action: str,
) -> tuple[
    str,
    str | None,
    str | None,
    list[EventContextItem],
    list[EventChangeItem],
    EventDetailSection | None,
    list[EventDetailSection],
    str | None,
]:
    sample_label = sample_identifier or "Unknown sample"
    actor = username or "system"
    related_url = f"/samples/{event.sample_id}" if event.sample_id else None

    if display_action == "create_sample":
        snapshot = payload.get("snapshot") or _sample_snapshot_from_model(event.sample)
        audit_title = _sample_audit_title(snapshot, sample_identifier)
        return (
            audit_title,
            None,
            None,
            _compact_pills(
                EventContextItem(label="User", value=actor),
                EventContextItem(label="Study Role", value=_study_role_label(payload.get("study_role") or snapshot.get("study_role"))),
                EventContextItem(label="Custody", value=_value_label(snapshot.get("custody"))),
                EventContextItem(label="Study", value=str(snapshot.get("study") or "--")),
            ),
            [],
            _sample_metadata_section("Metadata", snapshot),
            [],
            related_url,
        )

    if display_action == "update_sample":
        after_snapshot = payload.get("after") or _sample_snapshot_from_model(event.sample)
        audit_title = _sample_audit_title(after_snapshot, sample_identifier)
        if event.event_type == models.EventType.status_change:
            before_snapshot = payload.get("before") or {}
            change_items = _event_change_items(payload)
            detail_sections = [
                EventDetailSection(
                    title="Custody change",
                    layout="compact",
                    items=_compact_section_items(
                        EventContextItem(label="Previous custody", value=_value_label(before_snapshot.get("custody"))),
                        EventContextItem(label="New custody", value=_value_label(after_snapshot.get("custody"))),
                        EventContextItem(label="Archive note", value=str(payload.get("note") or "--")),
                    ),
                )
            ]
            return (
                audit_title,
                None,
                None,
                _compact_pills(
                    EventContextItem(label="User", value=actor),
                    EventContextItem(label="Changed", value="1"),
                ),
                change_items,
                _sample_metadata_section("Current metadata", after_snapshot),
                detail_sections,
                related_url,
            )

        change_items = _event_change_items(payload)
        return (
            audit_title,
            None,
            None,
            _compact_pills(
                EventContextItem(label="User", value=actor),
                EventContextItem(label="Changed", value=str(len(change_items)) if change_items else "--"),
            ),
            change_items,
            _sample_metadata_section("Current metadata", after_snapshot),
            [],
            related_url,
        )

    if display_action == "analyze_sample":
        after_snapshot = payload.get("after") or _sample_snapshot_from_model(event.sample)
        analysis_type = str(payload.get("analysis_type") or "Analysis")
        disposition = "Returned to storage" if payload.get("returned_to_storage") else "Out for analysis"
        previous = _display_path(payload.get("from_path") or _position_context(event.from_position, event.from_position_id))
        new = _display_path(payload.get("to_path")) if payload.get("returned_to_storage") else "Out for analysis"
        change_items = _event_change_items(payload)
        return (
            _sample_audit_title(after_snapshot, sample_identifier),
            f"{analysis_type} | {disposition}",
            None,
            _compact_pills(
                EventContextItem(label="User", value=actor),
                EventContextItem(label="Disposition", value="Returned" if payload.get("returned_to_storage") else "Out for analysis"),
                EventContextItem(label="Thaw", value=f"+{payload.get('thaw_increment', 0)}"),
            ),
            change_items,
            _sample_metadata_section("Current metadata", after_snapshot),
            [
                EventDetailSection(
                    title="Analysis details",
                    layout="compact",
                    items=_compact_section_items(
                        EventContextItem(label="Type", value=analysis_type),
                        EventContextItem(label="Performed", value=_display_datetime(str(payload.get("performed_at") or ""))),
                        EventContextItem(label="Disposition", value=disposition),
                        EventContextItem(label="Batch ID", value=str(payload.get("analysis_batch_id") or "--")),
                        EventContextItem(label="Batch notes", value=str(payload.get("overall_notes") or "--")),
                        EventContextItem(label="Sample notes", value=str(payload.get("sample_notes") or "--")),
                    ),
                ),
                EventDetailSection(
                    title="Location outcome",
                    layout="compact",
                    items=_compact_section_items(
                        EventContextItem(label="Withdrawn from", value=previous),
                        EventContextItem(label="Final location", value=new),
                    ),
                ),
            ],
            related_url,
        )

    if display_action == "place_sample":
        snapshot = _sample_snapshot_from_model(event.sample)
        destination = _display_path(payload.get("to_path") or _position_context(event.to_position, event.to_position_id))
        return (
            _sample_audit_title(snapshot, sample_identifier),
            destination,
            None,
            _compact_pills(EventContextItem(label="User", value=actor)),
            [],
            None,
            [EventDetailSection(title="Location", layout="single_value", items=[EventContextItem(label="", value=destination)])],
            related_url,
        )

    if display_action == "move_sample":
        snapshot = _sample_snapshot_from_model(event.sample)
        previous = _display_path(payload.get("from_path") or _position_context(event.from_position, event.from_position_id))
        new = _display_path(payload.get("to_path") or _position_context(event.to_position, event.to_position_id))
        return (
            _sample_audit_title(snapshot, sample_identifier),
            f"{previous} -> {new}",
            None,
            _compact_pills(EventContextItem(label="User", value=actor)),
            [],
            None,
            [
                EventDetailSection(
                    title="Location change",
                    layout="compact",
                    items=[
                        EventContextItem(label="Previous location", value=previous),
                        EventContextItem(label="New location", value=new),
                    ],
                )
            ],
            related_url,
        )

    if display_action == "delete_sample":
        location_value = _display_path(payload.get("location_path") or payload.get("location_label") or "Unplaced")
        final_snapshot = payload.get("snapshot") or _delete_snapshot(payload)
        final_section = _sample_metadata_section("Final record", final_snapshot)
        final_items = list(final_section.items) if final_section else []
        final_items.extend(
            [
                EventContextItem(label="Final custody", value=_value_label(payload.get("custody") or final_snapshot.get("custody"))),
                EventContextItem(label="Last location", value=location_value),
            ]
        )
        return (
            _sample_audit_title(final_snapshot, sample_identifier),
            None,
            None,
            _compact_pills(
                EventContextItem(label="User", value=actor),
                EventContextItem(label="Final custody", value=_value_label(payload.get("custody") or final_snapshot.get("custody"))),
            ),
            [],
            EventDetailSection(title="Final record", layout="full", items=final_items),
            [],
            None,
        )

    if event.event_type == models.EventType.create_storage:
        return _format_storage_event(payload, actor, display_action)

    if event.event_type == models.EventType.add_note:
        note_text = str(payload.get("text") or "Note recorded")
        return (
            sample_label,
            None,
            None,
            _compact_pills(EventContextItem(label="User", value=actor)),
            [],
            None,
            [EventDetailSection(title="Note", layout="compact", items=[EventContextItem(label="Text", value=note_text)])],
            related_url,
        )

    return (
        sample_label,
        None,
        None,
        _compact_pills(EventContextItem(label="User", value=actor)),
        [],
        None,
        [],
        related_url,
    )


def _batch_group_key(view: EventView) -> tuple[str, str] | None:
    kind = str(view.raw_payload.get("batch_group_kind") or "").strip()
    group_id = str(view.raw_payload.get("batch_group_id") or "").strip()
    if not kind or not group_id:
        return None
    return (kind, group_id)


def _build_group_parent_view(children: list[EventView]) -> EventView:
    first = children[0]
    latest = max(children, key=lambda item: item.created_at)
    group_kind, group_id = _batch_group_key(first) or ("batch", str(first.id))
    source_payload = dict(first.raw_payload or {})
    title = str(source_payload.get("batch_group_title") or first.action_label or "Batch activity")
    recorded = latest.created_at.strftime("%m/%d/%y %H:%M")
    workflow_type = str(
        source_payload.get("batch_workflow_label")
        or source_payload.get("analysis_type")
        or source_payload.get("batch_group_kind")
        or first.action_label
    )
    action_label = str(source_payload.get("batch_action_label") or first.action_label)
    sample_count = int(source_payload.get("batch_sample_count") or len(children))
    count_label = str(source_payload.get("batch_count_label") or "Samples").strip() or "Samples"
    destination = _display_path(str(source_payload.get("batch_destination_path") or "").strip())
    returned_count = source_payload.get("batch_returned_count")
    out_for_analysis_count = source_payload.get("batch_out_for_analysis_count")
    if out_for_analysis_count is None:
        out_for_analysis_count = source_payload.get("batch_archived_count")
    has_disposition_counts = returned_count is not None or out_for_analysis_count is not None or any(
        child.raw_payload.get("returned_to_storage") is not None for child in children
    )
    returned_count = int(returned_count or sum(1 for child in children if child.raw_payload.get("returned_to_storage") is True))
    out_for_analysis_count = int(
        out_for_analysis_count or sum(1 for child in children if child.raw_payload.get("returned_to_storage") is False)
    )
    performed = _display_datetime(str(source_payload.get("performed_at") or ""))
    visit_date = _display_datetime(str(source_payload.get("visit_date") or ""))
    participant_id = str(source_payload.get("participant_id") or "").strip()
    notes = str(source_payload.get("overall_notes") or source_payload.get("session_notes") or "--")
    payload = {
        "batch_group_kind": group_kind,
        "batch_group_id": group_id,
        "batch_group_title": title,
        "batch_sample_count": sample_count,
        "batch_returned_count": returned_count,
        "batch_out_for_analysis_count": out_for_analysis_count,
        "analysis_type": source_payload.get("analysis_type"),
        "performed_at": source_payload.get("performed_at"),
        "overall_notes": source_payload.get("overall_notes"),
        "participant_id": source_payload.get("participant_id"),
        "visit_date": source_payload.get("visit_date"),
        "session_notes": source_payload.get("session_notes"),
        "uploaded_workbook_filename": source_payload.get("uploaded_workbook_filename"),
        "group_event_ids": [child.id for child in children],
    }
    group_summary = [
        EventContextItem(label="Workflow", value=workflow_type),
        EventContextItem(label="Recorded", value=recorded),
    ]
    if performed != "--":
        group_summary.append(EventContextItem(label="Performed", value=performed))
    if visit_date != "--":
        group_summary.append(EventContextItem(label="Visit date", value=visit_date))
    if participant_id:
        group_summary.append(EventContextItem(label="Participant", value=participant_id))
    group_summary.extend(
        [
            EventContextItem(label="Operator", value=latest.username or "system"),
            EventContextItem(label=count_label, value=str(sample_count)),
        ]
    )
    if destination and destination != "--":
        group_summary.append(EventContextItem(label="Destination", value=destination))
    if has_disposition_counts:
        group_summary.extend(
            [
                EventContextItem(label="Returned", value=str(returned_count)),
                EventContextItem(label="Out for analysis", value=str(out_for_analysis_count)),
            ]
        )
    if notes != "--":
        group_summary.append(EventContextItem(label="Notes", value=notes))
    context_parts = [workflow_type, f"{sample_count} {count_label.lower()}"]
    if participant_id:
        context_parts.append(participant_id)
    if destination and destination != "--":
        context_parts.append(destination)
    if has_disposition_counts:
        context_parts.append(f"{returned_count} returned")
        context_parts.append(f"{out_for_analysis_count} out")
    context_line = " | ".join(context_parts)
    pill_items = [
        EventContextItem(label="User", value=latest.username or "system"),
        EventContextItem(label=count_label, value=str(sample_count)),
    ]
    if has_disposition_counts:
        pill_items.extend(
            [
                EventContextItem(label="Returned", value=str(returned_count)),
                EventContextItem(label="Out", value=str(out_for_analysis_count)),
            ]
        )
    pill_items = _compact_pills(*pill_items)
    group_items = [_build_group_item(child) for child in sorted(children, key=lambda item: item.sample_identifier or item.title)]
    risk_level = "high" if out_for_analysis_count else max(children, key=lambda item: _risk_rank(item.risk_level)).risk_level
    return EventView(
        id=latest.id,
        event_type=first.event_type,
        display_action=first.display_action,
        sample_id=None,
        sample_identifier=None,
        user_id=latest.user_id,
        username=latest.username,
        from_position_id=None,
        to_position_id=None,
        payload=payload,
        raw_payload=payload,
        action_label=action_label,
        summary=f"{action_label}: {title}",
        title=title,
        context_line=context_line,
        drawer_context_line=context_line,
        subtitle=context_line,
        pill_items=pill_items,
        primary_items=pill_items,
        context_items=pill_items,
        detail_items=list(group_summary),
        change_items=[],
        metadata_section=EventDetailSection(title="Batch Summary", layout="compact", items=group_summary),
        detail_sections=[],
        risk_level=risk_level,
        is_high_risk=risk_level == "high",
        has_legacy_detail_gap=False,
        severity=_severity_for_risk(risk_level),
        related_url=None,
        is_group_parent=True,
        group_kind=group_kind,
        group_id=group_id,
        group_title=title,
        group_count=sample_count,
        group_expanded_default=False,
        group_children=group_items,
        created_at=latest.created_at,
    )


def _build_group_item(event: EventView) -> EventGroupItem:
    volume_change = next((f"{change.before} -> {change.after}" for change in event.change_items if change.label == "Volume"), None)
    if event.raw_payload.get("returned_to_storage") is True:
        disposition = "Returned"
        location_outcome = _display_path(event.raw_payload.get("to_path"))
    elif event.raw_payload.get("returned_to_storage") is False:
        disposition = "Out for analysis"
        location_outcome = "Out for analysis"
    else:
        disposition = event.action_label
        location_outcome = event.context_line
    thaw_increment = event.raw_payload.get("thaw_increment")
    return EventGroupItem(
        event_id=event.id,
        sample_id=event.sample_id,
        sample_identifier=event.sample_identifier,
        title=event.title,
        disposition=disposition,
        volume_change=volume_change,
        thaw_increment=f"+{thaw_increment}" if thaw_increment not in (None, "") else None,
        location_outcome=location_outcome,
        context_line=event.context_line,
        related_url=event.related_url,
    )


def _format_storage_event(
    payload: dict,
    actor: str,
    display_action: str,
) -> tuple[
    str,
    str | None,
    str | None,
    list[EventContextItem],
    list[EventChangeItem],
    EventDetailSection | None,
    list[EventDetailSection],
    str,
]:
    node_name = str(payload.get("name") or payload.get("node_id") or "Storage item")
    node_type = str(payload.get("node_type") or "storage").replace("_", " ").title()
    path = _display_path(str(payload.get("path") or payload.get("after_path") or payload.get("before_path") or node_name))
    change_items = _event_change_items(payload)

    if display_action == "create_box":
        summary = _box_grid_summary(payload)
        return (
            node_name,
            summary,
            None,
            _compact_pills(EventContextItem(label="User", value=actor)),
            [],
            None,
            [
                EventDetailSection(
                    title="Box details",
                    layout="compact",
                    items=_compact_section_items(
                        EventContextItem(label="Path", value=path),
                        EventContextItem(label="Rows", value=str(payload.get("rows") or "--")),
                        EventContextItem(label="Cols", value=str(payload.get("cols") or "--")),
                        EventContextItem(label="Positions", value=str(payload.get("positions") or "--")),
                    ),
                )
            ],
            "/storage",
        )

    if display_action == "move_storage":
        before_path = _display_path(str(payload.get("before_path") or path))
        after_path = _display_path(str(payload.get("after_path") or path))
        before_slot = str(payload.get("before_slot") or "").strip()
        after_slot = str(payload.get("after_slot") or "").strip()
        location_items = [
            EventContextItem(label="Previous path", value=before_path),
            EventContextItem(label="New path", value=after_path),
        ]
        if before_slot or after_slot:
            location_items.extend(
                [
                    EventContextItem(label="Previous rack position", value=before_slot or "--"),
                    EventContextItem(label="New rack position", value=after_slot or "--"),
                ]
            )
        return (
            node_name,
            after_slot if after_slot else after_path,
            None,
            _compact_pills(
                EventContextItem(label="User", value=actor),
                EventContextItem(label="Type", value=node_type),
            ),
            [],
            None,
            [
                EventDetailSection(
                    title="Location change",
                    layout="compact",
                    items=location_items,
                )
            ],
            "/storage",
        )

    if display_action == "update_storage":
        return (
            node_name,
            None,
            None,
            _compact_pills(
                EventContextItem(label="User", value=actor),
                EventContextItem(label="Type", value=node_type),
            ),
            change_items,
            None,
            [],
            "/storage",
        )

    if display_action == "delete_storage":
        return (
            node_name,
            None,
            None,
            _compact_pills(
                EventContextItem(label="User", value=actor),
                EventContextItem(label="Type", value=node_type),
            ),
            [],
            None,
            [
                EventDetailSection(
                    title="Storage details",
                    layout="compact",
                    items=[
                        EventContextItem(label="Type", value=node_type),
                        EventContextItem(label="Last path", value=path),
                    ],
                )
            ],
            "/storage",
        )

    return (
        node_name,
        path,
        None,
        _compact_pills(
            EventContextItem(label="User", value=actor),
            EventContextItem(label="Type", value=node_type),
        ),
        [],
        None,
        [
            EventDetailSection(
                title="Storage details",
                layout="compact",
                items=[
                    EventContextItem(label="Type", value=node_type),
                    EventContextItem(label="Path", value=path),
                ],
            )
        ],
        "/storage",
    )


def _sample_snapshot_from_model(sample: models.Sample | None) -> dict[str, str]:
    if sample is None:
        return {}
    return {
        "sample_id": sample.sample_id,
        "type": sample.sample_type.name if sample.sample_type else "--",
        "study": sample.study.display_name if sample.study else "--",
        "visit": sample.visit_label or "--",
        "timepoint": sample.timepoint_label or "--",
        "aliquot": str(sample.aliquot_number) if sample.aliquot_number is not None else "--",
        "hemolysis": str(sample.hemolysis_classification) if sample.hemolysis_classification is not None else "--",
        "study_role": sample.study_role.value,
        "custody": "archived" if sample.is_archived else ("out_for_analysis" if sample.is_out_for_analysis else ("in_storage" if sample.location else "unplaced")),
        "usage": "used" if sample.thaw_count > 0 else "unused",
        "volume": _volume_display(sample.volume, sample.volume_units),
        "thaw_count": str(sample.thaw_count),
        "notes": sample.notes or "--",
        "collection": sample.collection_at.strftime("%m/%d/%y %H:%M") if sample.collection_at else "--",
    }


def _sample_metadata_section(title: str, snapshot: dict | None) -> EventDetailSection | None:
    if not snapshot:
        return None
    items = _compact_section_items(
        EventContextItem(label="ID", value=str(snapshot.get("sample_id") or "--")),
        EventContextItem(label="Type", value=str(snapshot.get("type") or "--")),
        EventContextItem(label="Study", value=str(snapshot.get("study") or "--")),
        EventContextItem(label="Visit", value=str(snapshot.get("visit") or "--")),
        EventContextItem(label="Timepoint", value=str(snapshot.get("timepoint") or "--")),
        EventContextItem(label="Aliquot", value=str(snapshot.get("aliquot") or "--")),
        EventContextItem(label="Hemolysis", value=str(snapshot.get("hemolysis") or "--")),
        EventContextItem(label="Study Role", value=_study_role_label(str(snapshot.get("study_role") or "--"))),
        EventContextItem(label="Custody", value=_value_label(str(snapshot.get("custody") or "--"))),
        EventContextItem(label="Usage", value=_value_label(str(snapshot.get("usage") or "--"))),
        EventContextItem(label="Volume", value=str(snapshot.get("volume") or "--")),
        EventContextItem(label="Thaw count", value=str(snapshot.get("thaw_count") or "--")),
        EventContextItem(label="Collection", value=str(snapshot.get("collection") or "--")),
        EventContextItem(label="Notes", value=str(snapshot.get("notes") or "--")),
    )
    return EventDetailSection(title=title, layout="full", items=items)


def _sample_identity_line(snapshot: dict | None) -> str | None:
    if not snapshot:
        return None
    parts: list[str] = []
    sample_type = str(snapshot.get("type") or "").strip()
    if sample_type and sample_type != "--":
        parts.append(sample_type)
    visit = str(snapshot.get("visit") or "").strip()
    if visit and visit != "--":
        parts.append(visit)
    timepoint = str(snapshot.get("timepoint") or "").strip()
    if timepoint and timepoint != "--":
        parts.append(timepoint)
    aliquot = str(snapshot.get("aliquot") or "").strip()
    if aliquot and aliquot != "--":
        parts.append(f"#{aliquot}")
    collection = str(snapshot.get("collection") or "").strip()
    if collection and collection != "--":
        parts.append(collection.split(" ")[0])
    return " · ".join(parts) if parts else None


def _sample_audit_title(snapshot: dict | None, sample_identifier: str | None) -> str:
    identifier = str((snapshot or {}).get("sample_id") or sample_identifier or "").strip()
    if not identifier or identifier == "--":
        identifier = sample_identifier or "Unknown sample"

    parts = [identifier]
    if snapshot:
        sample_type = str(snapshot.get("type") or "").strip()
        if sample_type and sample_type != "--":
            parts.append(sample_type)
        visit = str(snapshot.get("visit") or "").strip()
        if visit and visit != "--":
            parts.append(_prefixed_code(visit, "V", "VISIT"))
        timepoint = str(snapshot.get("timepoint") or "").strip()
        if timepoint and timepoint != "--":
            parts.append(_prefixed_code(timepoint, "T", "TIMEPOINT"))
        aliquot = str(snapshot.get("aliquot") or "").strip()
        if aliquot and aliquot != "--":
            parts.append(f"#{aliquot}")
    return " ".join(parts)


def _prefixed_code(value: str, prefix: str, long_label: str) -> str:
    cleaned = value.strip()
    upper = cleaned.upper()
    if upper.startswith(prefix):
        return f"{prefix}{cleaned[1:].strip()}"
    if upper.startswith(long_label):
        suffix = cleaned[len(long_label):].strip()
        return f"{prefix}{suffix}" if suffix else prefix
    if cleaned[:1].isdigit():
        return f"{prefix}{cleaned}"
    return cleaned


def _delete_snapshot(payload: dict) -> dict[str, str]:
    return {
        "sample_id": str(payload.get("sample_identifier") or "--"),
        "type": str(payload.get("sample_type") or "--"),
        "study": str(payload.get("study") or "--"),
        "visit": str(payload.get("visit") or "--"),
        "timepoint": str(payload.get("timepoint") or "--"),
        "aliquot": str(payload.get("aliquot") or "--"),
        "hemolysis": str(payload.get("hemolysis") or "--"),
        "study_role": str(payload.get("study_role") or "--"),
        "custody": str(payload.get("custody") or "--"),
        "usage": str(payload.get("usage") or "--"),
        "volume": str(payload.get("volume") or "--"),
        "thaw_count": str(payload.get("thaw_count") or "--"),
        "notes": str(payload.get("notes") or "--"),
        "collection": str(payload.get("collection") or "--"),
    }


def _event_change_items(payload: dict) -> list[EventChangeItem]:
    return [
        EventChangeItem(
            field=str(change.get("field") or ""),
            label=str(change.get("label") or change.get("field") or ""),
            before=str(change.get("before") or "--"),
            after=str(change.get("after") or "--"),
        )
        for change in payload.get("changes", [])
    ]


def _display_action(event, payload: dict) -> str:
    if event.event_type == models.EventType.status_change:
        return "update_sample"
    if event.event_type != models.EventType.create_storage:
        return event.event_type.value
    action = str(payload.get("action") or "create")
    node_type = str(payload.get("node_type") or "")
    if action in {"create_box", "generate_positions"}:
        return "create_box"
    if action == "create":
        return "create_box" if node_type == "box" else "create_storage"
    if action == "update":
        return "update_storage"
    if action == "move":
        return "move_storage"
    if action == "delete":
        return "delete_storage"
    return "create_storage"


def _risk_level(event, payload: dict, display_action: str) -> str:
    if display_action in {"delete_sample", "delete_storage"}:
        return "high"
    if display_action == "analyze_sample" and not payload.get("returned_to_storage"):
        return "high"
    if display_action == "analyze_sample":
        return "medium"
    if event.event_type == models.EventType.status_change and (payload.get("after") or {}).get("custody") == "archived":
        return "high"
    if display_action in {"move_sample", "move_storage", "update_sample"} and event.event_type == models.EventType.status_change:
        return "medium"
    if display_action in {"move_sample", "move_storage"}:
        return "medium"
    return "low"


def _severity_for_risk(risk_level: str) -> str:
    if risk_level == "high":
        return "warning"
    if risk_level == "medium":
        return "neutral"
    return "success"


def _risk_rank(risk_level: str) -> int:
    if risk_level == "high":
        return 3
    if risk_level == "medium":
        return 2
    return 1


def _has_legacy_detail_gap(event, payload: dict, change_items: list[EventChangeItem]) -> bool:
    if event.event_type == models.EventType.update_sample and not change_items:
        return True
    if event.event_type == models.EventType.create_storage and payload.get("action") == "update" and not change_items:
        return True
    return False


def _position_context(position: models.StoragePosition | None, position_id: int | None) -> str:
    if position is not None:
        return storage_service.storage_path_for_position(position)
    if position_id is not None:
        return f"Position ID {position_id}"
    return "Unknown position"


def _study_role_label(value: str | None) -> str:
    if not value:
        return "--"
    if value == "current":
        return "Current"
    if value == "retired":
        return "Retired"
    return value.replace("_", " ")


def _value_label(value: str | None) -> str:
    if not value:
        return "--"
    return value.replace("_", " ")


def _labelize(value: str) -> str:
    return value.replace("_", " ").title()


def _volume_display(volume: float | None, units: str | None) -> str:
    if volume is None:
        return "--"
    return f"{volume:g} {units or 'mL'}"


def _display_path(value: str | None) -> str:
    if not value:
        return "--"
    return value.replace("/", " > ")


def _display_datetime(value: str | None) -> str:
    if not value:
        return "--"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%m/%d/%y %H:%M")


def _box_grid_summary(payload: dict) -> str | None:
    rows = payload.get("rows")
    cols = payload.get("cols")
    positions = payload.get("positions")
    parts: list[str] = []
    if rows and cols:
        parts.append(f"{rows} x {cols}")
    if positions:
        parts.append(f"{positions} positions")
    return " · ".join(parts) if parts else None


def _compact_pills(*items: EventContextItem | None) -> list[EventContextItem]:
    return [item for item in items if item and item.value and item.value != "--"]


def _compact_section_items(*items: EventContextItem | None) -> list[EventContextItem]:
    return [item for item in items if item and item.value and item.value != "--"]
