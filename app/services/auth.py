from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.domain import models
from app.repositories import users


class PermissionError(Exception):
    pass


class UserManagementError(Exception):
    pass


PERMISSION_DEFINITIONS = [
    {"key": "manage_users", "label": "Manage Users & Roles", "description": "Edit users, roles, and permission overrides."},
    {"key": "manage_vocabularies", "label": "Manage Studies & Types", "description": "Create, edit, and delete studies and sample types."},
    {"key": "manage_storage_tree", "label": "Manage Storage Tree", "description": "Create, edit, move, delete, and generate storage structure."},
    {"key": "bulk_import_storage", "label": "Bulk Import Storage", "description": "Use storage bulk import and storage templates."},
    {"key": "bulk_import_samples", "label": "Bulk Import Samples", "description": "Use sample bulk import and sample templates."},
    {"key": "edit_samples", "label": "Create & Edit Samples", "description": "Register samples, edit sample records, and add notes."},
    {"key": "process_analysis", "label": "Process Analysis", "description": "Run analysis batches that update volume, thaw counts, and storage outcomes."},
    {"key": "archive_samples", "label": "Archive Samples", "description": "Archive samples out of active freezer inventory."},
    {"key": "delete_samples", "label": "Delete Samples", "description": "Permanently delete samples with audit tracking."},
    {"key": "place_move_samples", "label": "Place & Move Samples", "description": "Place samples into boxes and move them between positions."},
    {"key": "export_data", "label": "Export Data", "description": "Download export snapshots and operational data bundles."},
]
PERMISSION_KEYS = {item["key"] for item in PERMISSION_DEFINITIONS}
ROLE_DEFAULT_PERMISSIONS = {
    models.UserRole.admin: set(PERMISSION_KEYS),
    models.UserRole.staff: {"bulk_import_samples", "edit_samples", "process_analysis", "archive_samples", "place_move_samples"},
}


def sync_user(
    db: Session,
    username: str,
    full_name: str | None = None,
) -> models.User:
    user = users.get_by_username(db, username)
    if user is None:
        role = models.UserRole.admin if users.count_users(db) == 0 else models.UserRole.staff
        user = models.User(username=username, full_name=full_name, role=role)
        db.add(user)
    else:
        if full_name and not user.full_name:
            user.full_name = full_name
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_profile(
    db: Session,
    user: models.User,
    *,
    full_name: str | None,
) -> models.User:
    user.full_name = full_name
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[models.User]:
    return users.list_users(db)


def update_user_admin(
    db: Session,
    actor: models.User,
    target_user_id: int,
    *,
    full_name: str | None,
    role: str,
    permissions: list[str],
) -> models.User:
    require_permission(actor, "manage_users")
    user = users.get_by_id(db, target_user_id)
    if user is None:
        raise UserManagementError("User was not found")
    next_role = models.UserRole(role)
    selected_permissions = normalize_permissions(permissions)
    if "manage_users" not in selected_permissions and has_permission(user, "manage_users") and count_users_with_permission(db, "manage_users") <= 1:
        raise UserManagementError("At least one user must retain permission to manage users and roles")
    user.full_name = full_name
    user.role = next_role
    allow, deny = build_permission_overrides(next_role, selected_permissions)
    user.permissions_allow_json = _dump_permissions(allow)
    user.permissions_deny_json = _dump_permissions(deny)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def require_admin(user: models.User | None) -> None:
    if user is None or user.role != models.UserRole.admin:
        raise PermissionError("Admin access required")


def list_permission_definitions() -> list[dict[str, str]]:
    return [dict(item) for item in PERMISSION_DEFINITIONS]


def default_permissions_for_role(role: str | models.UserRole) -> set[str]:
    role_value = role if isinstance(role, models.UserRole) else models.UserRole(role)
    return set(ROLE_DEFAULT_PERMISSIONS.get(role_value, set()))


def effective_permissions(user: models.User | None) -> set[str]:
    if user is None:
        return set()
    permissions = default_permissions_for_role(user.role)
    permissions.update(_load_permissions(user.permissions_allow_json))
    permissions.difference_update(_load_permissions(user.permissions_deny_json))
    return permissions


def has_permission(user: models.User | None, permission: str) -> bool:
    return permission in effective_permissions(user)


def require_permission(user: models.User | None, permission: str) -> None:
    if user is None or not has_permission(user, permission):
        raise PermissionError("Permission denied")


def count_users_with_permission(db: Session, permission: str) -> int:
    return sum(1 for user in users.list_users(db) if has_permission(user, permission))


def normalize_permissions(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        if value in PERMISSION_KEYS and value not in normalized:
            normalized.append(value)
    return normalized


def build_permission_overrides(role: str | models.UserRole, selected_permissions: list[str] | set[str]) -> tuple[list[str], list[str]]:
    defaults = default_permissions_for_role(role)
    selected = set(normalize_permissions(list(selected_permissions)))
    allow = sorted(selected - defaults)
    deny = sorted(defaults - selected)
    return allow, deny


def _load_permissions(raw: str | None) -> set[str]:
    if not raw:
        return set()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(values, list):
        return set()
    return {value for value in values if value in PERMISSION_KEYS}


def _dump_permissions(values: list[str]) -> str | None:
    if not values:
        return None
    return json.dumps(values)
