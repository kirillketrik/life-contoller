"""Centralized role/permission decisions.

Views and DRF permission classes must never hardcode `is_staff`/`is_superuser`
checks directly. Instead they ask `PermissionService` "can this user do X to
resource Y" and it decides based on role membership. To grant a new role
access to something later, extend `_ROLE_PERMISSIONS` (or `roles_for`, if the
new role isn't a Django Group) — no view/serializer changes required.
"""

from __future__ import annotations

from enum import Enum

from django.conf import settings


class Action(str, Enum):
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"


class Resource(str, Enum):
    METRIC_TYPE = "metric_type"
    METRIC_ENTRY = "metric_entry"


ADMIN_ROLE = "admin"

# role name -> set of (resource, action) it may perform, beyond what ownership
# already grants (e.g. viewing your own data is handled separately by scoping
# querysets to the requesting user, not through this table).
_ROLE_PERMISSIONS: dict[str, set[tuple[Resource, Action]]] = {
    ADMIN_ROLE: {
        (Resource.METRIC_TYPE, Action.CREATE),
        (Resource.METRIC_TYPE, Action.EDIT),
        (Resource.METRIC_TYPE, Action.DELETE),
        (Resource.METRIC_ENTRY, Action.CREATE),
        (Resource.METRIC_ENTRY, Action.EDIT),
        (Resource.METRIC_ENTRY, Action.DELETE),
    },
}


class PermissionService:
    @staticmethod
    def roles_for(user) -> set[str]:
        if not user or not user.is_authenticated:
            return set()
        roles = set(user.groups.values_list("name", flat=True))
        if user.is_superuser:
            roles.add(ADMIN_ROLE)
        return roles

    @classmethod
    def is_admin(cls, user) -> bool:
        return ADMIN_ROLE in cls.roles_for(user)

    @classmethod
    def can(cls, user, action: Action, resource: Resource) -> bool:
        roles = cls.roles_for(user)
        return any((resource, action) in _ROLE_PERMISSIONS.get(role, set()) for role in roles)


def admin_group_name() -> str:
    return getattr(settings, "ADMIN_ROLE_GROUP", ADMIN_ROLE)
