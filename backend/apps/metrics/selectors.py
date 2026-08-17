"""Read-only query logic for the metrics app.

Convention: views/viewsets never build querysets inline — they call a selector
here. Keeps scoping/ownership rules (who can see what) in one place per
resource instead of duplicated across `get_queryset` methods.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.core.permissions import PermissionService

from .models import MetricEntry, MetricType


def metric_type_list() -> QuerySet[MetricType]:
    """All metric types are shared, readable definitions — visible to any
    authenticated user."""
    return MetricType.objects.all()


def metric_type_get(*, metric_type_id: int) -> MetricType | None:
    return MetricType.objects.filter(id=metric_type_id).first()


def metric_entry_list_for_user(*, user, metric_type_id: int | None = None) -> QuerySet[MetricEntry]:
    """Entries owned by `user`; admins additionally see everyone's entries.
    Optionally narrowed to a single `MetricType`."""
    queryset = MetricEntry.objects.select_related("metric_type", "owner")
    if not PermissionService.is_admin(user):
        queryset = queryset.filter(owner=user)
    if metric_type_id is not None:
        queryset = queryset.filter(metric_type_id=metric_type_id)
    return queryset


def metric_entry_get_for_user(*, user, entry_id: int) -> MetricEntry | None:
    return metric_entry_list_for_user(user=user).filter(id=entry_id).first()
