from __future__ import annotations

from app.services import auth as auth_service

SELECTION_STORAGE_KEY = "sample-action-selection"
WORKSPACE_URL = "/sample-actions"

ACTION_REGISTRY = [
    {
        "action_key": "analyze",
        "label": "Batch Analyze",
        "description": "Generate an analysis workbook, fill it out offline, then upload it for validation and commit.",
        "instructions": (
            "Use this when selected samples were removed for analysis. Download the prefilled workbook, "
            "record remaining volume, return/archive outcome, thaw increment, and notes, then upload it for preview."
        ),
        "permission": "process_analysis",
        "workspace_url": "/sample-actions/analyze",
        "download_url": "/sample-actions/analyze/log",
        "preview_url": "/sample-actions/analyze/preview",
        "file_field": "analysis_file",
        "file_label": "Analysis workbook",
        "download_label": "Download analysis log",
        "upload_label": "Upload completed analysis log",
    },
    {
        "action_key": "modify",
        "label": "Batch Modify",
        "description": "Download a metadata workbook, edit the selected samples offline, then preview and commit the changes.",
        "instructions": (
            "Use this for metadata-only updates across selected samples. Download the workbook, edit the target values "
            "offline, then upload it for validation before committing changes."
        ),
        "permission": "edit_samples",
        "workspace_url": "/sample-actions/modify",
        "download_url": "/sample-actions/modify/log",
        "preview_url": "/sample-actions/modify/preview",
        "file_field": "modify_file",
        "file_label": "Batch modify workbook",
        "download_label": "Download modify template",
        "upload_label": "Upload completed modify workbook",
    },
]


def available_actions(user) -> list[dict[str, str]]:
    return [dict(action) for action in ACTION_REGISTRY if auth_service.has_permission(user, action["permission"])]


def has_any_actions(user) -> bool:
    return bool(available_actions(user))
