from __future__ import annotations

from app.services import auth as auth_service

SELECTION_STORAGE_KEY = "sample-action-selection"
WORKSPACE_URL = "/sample-actions"

ACTION_REGISTRY = [
    {
        "action_key": "analyze",
        "label": "Batch Analyze",
        "description": "Generate an analysis workbook, fill it out offline, then upload it for validation and commit.",
        "permission": "process_analysis",
        "workspace_url": "/sample-actions/analyze",
    },
    {
        "action_key": "modify",
        "label": "Batch Modify",
        "description": "Download a metadata workbook, edit the selected samples offline, then preview and commit the changes.",
        "permission": "edit_samples",
        "workspace_url": "/sample-actions/modify",
    },
]


def available_actions(user) -> list[dict[str, str]]:
    return [dict(action) for action in ACTION_REGISTRY if auth_service.has_permission(user, action["permission"])]


def has_any_actions(user) -> bool:
    return bool(available_actions(user))
