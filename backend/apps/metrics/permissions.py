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


class MetricEntryPermission(IsAdminOrReadOnly):
    resource = Resource.METRIC_ENTRY

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return PermissionService.is_admin(request.user) or obj.owner_id == request.user.id
        return super().has_object_permission(request, view, obj)
