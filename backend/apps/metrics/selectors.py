"""Read-only query logic for the metrics app.

Convention: views/viewsets never build querysets inline — they call a selector
here. Keeps scoping/ownership rules (who can see what) in one place per
resource instead of duplicated across `get_queryset` methods.
"""

from __future__ import annotations

from datetime import datetime

from django.db.models import QuerySet

from apps.core.permissions import PermissionService

from .aggregation import DataPoint
from .formulas import computed_series
from .models import FormulaDefinition, MetricEntry, MetricThreshold, MetricType


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


def points_for_metric_type(
    *, metric_type: MetricType, user, range_start: datetime, range_end: datetime
) -> list[DataPoint]:
    """The (timestamp, value) series for `metric_type` and `user` within a
    date range — from stored entries for a regular metric type, or evaluated
    on the fly from its `FormulaDefinition` for a computed one. Either way
    the result is the same `DataPoint` shape, ready for `apps.metrics.aggregation`.
    """
    if metric_type.is_computed:
        formula_definition = getattr(metric_type, "formula_definition", None)
        if formula_definition is None:
            return []
        return computed_series(
            formula_definition, user=user, range_start=range_start, range_end=range_end
        )

    entries = MetricEntry.objects.filter(
        metric_type=metric_type,
        owner=user,
        recorded_at__gte=range_start,
        recorded_at__lte=range_end,
    ).order_by("recorded_at")
    return [DataPoint(recorded_at=entry.recorded_at, value=entry.value) for entry in entries]


def metric_threshold_list_for_user(*, user) -> QuerySet[MetricThreshold]:
    return MetricThreshold.objects.filter(user=user).select_related("metric_type")


def metric_threshold_get_for_user(*, user, metric_type_id: int) -> MetricThreshold | None:
    return MetricThreshold.objects.filter(user=user, metric_type_id=metric_type_id).first()


def formula_definition_list() -> QuerySet[FormulaDefinition]:
    return FormulaDefinition.objects.select_related("computed_metric_type")


def formula_definition_get(*, formula_definition_id: int) -> FormulaDefinition | None:
    return FormulaDefinition.objects.filter(id=formula_definition_id).first()
