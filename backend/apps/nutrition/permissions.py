"""Thin DRF adapters, same two patterns as apps.metrics.permissions: role-
gated for the shared NutrientType catalog, plain ownership for a user's own
FoodItems. See the `architecture` skill's decision rule.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.permissions import Action, PermissionService, Resource


class NutrientTypePermission(BasePermission):
    """Any authenticated user may read the nutrient catalog; only admins
    define new entries — mirrors MetricTypePermission exactly."""

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
        return PermissionService.can(request.user, action, Resource.NUTRIENT_TYPE)

    def has_object_permission(self, request, view, obj) -> bool:
        return self.has_permission(request, view)


class FoodItemPermission(BasePermission):
    """Every authenticated user manages their own food items only — not a
    shared catalog, no admin override, same ownership pattern as
    MetricEntryPermission/MetricThresholdPermission."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.owner_id == request.user.id


class MealEntryPermission(BasePermission):
    """Every authenticated user manages their own logged meals only — same
    ownership pattern as FoodItemPermission."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.owner_id == request.user.id
