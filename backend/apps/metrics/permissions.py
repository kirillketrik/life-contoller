"""Thin DRF adapters over `apps.core.permissions.PermissionService`.

These classes hold no role logic of their own — they translate a DRF request
into an (Action, Resource) pair and ask the central service. Adding a new
role/permission mapping never requires touching these classes.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.permissions import Action, PermissionService, Resource


class IsAdminOrReadOnly(BasePermission):
    """Base: any authenticated user may read; writes require the given
    (resource, action-per-method) mapping to be granted by PermissionService.
    """

    resource: Resource

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True

        action = {
            "POST": Action.CREATE,
            "PUT": Action.EDIT,
            "PATCH": Action.EDIT,
            "DELETE": Action.DELETE,
        }.get(request.method)
        if action is None:
            return False
        return PermissionService.can(request.user, action, self.resource)

    def has_object_permission(self, request, view, obj) -> bool:
        return self.has_permission(request, view)


class MetricTypePermission(IsAdminOrReadOnly):
    resource = Resource.METRIC_TYPE


class MetricEntryPermission(BasePermission):
    """Every authenticated user may log entries for themselves and manage
    their own; admins may manage everyone's, consistent with them being able
    to read everyone's entries too (`selectors.metric_entry_list_for_user`).

    Unlike `MetricType` (an admin-defined shared catalog of what *can* be
    tracked), logging a reading against it is a personal action any user
    should be able to take — so this isn't role-gated through
    `PermissionService` the way `MetricTypePermission` is; it's ownership,
    same as `MetricThresholdPermission`.
    """

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        return PermissionService.is_admin(request.user) or obj.owner_id == request.user.id


class MetricThresholdPermission(BasePermission):
    """Every authenticated user manages their own thresholds. This is a
    personal preference, not a role-gated action, so it doesn't go through
    `PermissionService` — it's plain ownership, checked directly.
    """

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.user_id == request.user.id


class FormulaDefinitionPermission(BasePermission):
    """Admin-only for every action, including reads. Unlike MetricType/
    MetricEntry (shared read-only reference data for any authenticated
    user), formula definitions are only ever viewed/edited by admins — the
    frontend UI for them is admin-only too, per the same rule.
    """

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        action = {
            "GET": Action.VIEW,
            "HEAD": Action.VIEW,
            "OPTIONS": Action.VIEW,
            "POST": Action.CREATE,
            "PUT": Action.EDIT,
            "PATCH": Action.EDIT,
            "DELETE": Action.DELETE,
        }.get(request.method)
        if action is None:
            return False
        return PermissionService.can(request.user, action, Resource.FORMULA_DEFINITION)

    def has_object_permission(self, request, view, obj) -> bool:
        return self.has_permission(request, view)
