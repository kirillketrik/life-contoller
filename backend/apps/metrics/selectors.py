"""Read-only query logic for the metrics app.

Convention: views/viewsets never build querysets inline — they call a selector
here. Keeps scoping/ownership rules (who can see what) in one place per
resource instead of duplicated across `get_queryset` methods.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Count, QuerySet
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .aggregation import (
    DataPoint,
    period_percent_changes,
    resolve_named_range,
    summarize,
    time_in_range_percent,
)
from .formula_engine import computed_series, evaluate_formula
from .models import (
    DashboardElement,
    FormulaDefinition,
    MetricEntry,
    MetricImportSettings,
    MetricThreshold,
    MetricType,
)

DASHBOARD_TREND_MONTHS = 12

# The KPI badges shown next to a metric's name (dashboard element block and
# the metric detail page alike) — always "as of now", independent of
# whatever display timeframe the chart itself is currently showing.
PERIOD_CHANGE_SPECS: list[tuple[str, timedelta | relativedelta]] = [
    ("24h", timedelta(hours=24)),
    ("7d", timedelta(days=7)),
    ("30d", timedelta(days=30)),
    ("3m", relativedelta(months=3)),
    ("1y", relativedelta(years=1)),
]
# Deliberately much wider than the longest period spec above ("1y") rather
# than matching it exactly: "value at or before the 1y-ago target" needs
# points *older* than that target to fall back to when nothing landed
# exactly on that day, so bounding the fetch to precisely 1 year back would
# put the target on the query's own edge and hide any older point entirely
# — same "100 years back" convention as the frontend's "Всё время" preset.
PERIOD_CHANGE_LOOKBACK = relativedelta(years=100)


def metric_type_list(*, search: str | None = None) -> QuerySet[MetricType]:
    """All metric types are shared, readable definitions — visible to any
    authenticated user. `search` filters by name, same
    `name__icontains` convention as `apps.nutrition.selectors.
    food_item_list_for_user`/`recipe_list_for_user`."""
    queryset = MetricType.objects.all()
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset


def metric_type_get(*, metric_type_id: int) -> MetricType | None:
    return MetricType.objects.filter(id=metric_type_id).first()


def metric_entry_list_for_user(*, user, metric_type_id: int | None = None) -> QuerySet[MetricEntry]:
    """Entries owned by `user` only — ownership-based like `MetricThreshold`,
    with no admin override. Logging entries is a personal action; an admin
    account is not entitled to see or manage another user's readings just by
    virtue of the role, same as thresholds and dashboard elements. Optionally
    narrowed to a single `MetricType`."""
    queryset = MetricEntry.objects.select_related("metric_type", "owner").filter(owner=user)
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


def period_changes_for_metric_type(*, metric_type: MetricType, user, at: datetime) -> dict:
    """% change over each of `PERIOD_CHANGE_SPECS` (24h/7d/30d/3m/1y) as of
    `at`, for `metric_type`/`user` — the badges shown next to a metric's
    name. Deliberately its own lookback window (up to a year back) rather
    than reusing whatever range a chart happens to be displaying, since the
    periods here are fixed regardless of the caller's selected timeframe."""
    range_start = at - PERIOD_CHANGE_LOOKBACK
    points = points_for_metric_type(
        metric_type=metric_type, user=user, range_start=range_start, range_end=at
    )
    return period_percent_changes(points, at=at, periods=PERIOD_CHANGE_SPECS)


def metric_threshold_list_for_user(*, user) -> QuerySet[MetricThreshold]:
    return MetricThreshold.objects.filter(user=user).select_related("metric_type")


def metric_threshold_get_for_user(*, user, metric_type_id: int) -> MetricThreshold | None:
    return MetricThreshold.objects.filter(user=user, metric_type_id=metric_type_id).first()


def current_value_for_metric_type(*, metric_type: MetricType, user, at: datetime):
    """The single latest value for `metric_type`/`user`, as of `at` —
    deliberately *not* derived from a `points_for_metric_type` range query,
    since "current" must stay correct even when the latest entry falls
    outside whatever display timeframe a chart/element happens to be using.
    """
    if metric_type.is_computed:
        formula_definition = getattr(metric_type, "formula_definition", None)
        if formula_definition is None:
            return None
        return evaluate_formula(formula_definition, user=user, at=at)

    entry = (
        MetricEntry.objects.filter(metric_type=metric_type, owner=user, recorded_at__lte=at)
        .order_by("-recorded_at")
        .first()
    )
    return entry.value if entry is not None else None


def dashboard_element_list_for_user(*, user) -> QuerySet[DashboardElement]:
    return DashboardElement.objects.filter(user=user).select_related("metric_type")


def dashboard_element_get_for_user(*, user, metric_type_id: int) -> DashboardElement | None:
    return DashboardElement.objects.filter(user=user, metric_type_id=metric_type_id).first()


def dashboard_element_stats(
    *,
    metric_type: MetricType,
    user,
    show_chart: bool,
    show_current: bool,
    show_max: bool,
    show_min: bool,
    show_avg: bool,
    show_time_in_range: bool,
    timeframe: str,
    custom_start=None,
    custom_end=None,
    at: datetime,
) -> dict:
    """Resolves one `DashboardElement`-shaped config into its displayed
    values: `current` (always latest, unfiltered) and/or the chart's raw
    point series plus max/min/avg/time-in-range over the same resolved
    timeframe range — the same range feeds all of them, per the model's
    contract. Shared by the batched `/api/dashboard-elements/` endpoint
    (looped, one call per element) and the per-metric-type write action, so
    there's exactly one place this resolution logic lives.
    """
    result: dict = {
        "current": None,
        "max": None,
        "min": None,
        "avg": None,
        "time_in_range_percent": None,
        "points": [],
        "timeframe_unit": None,
        "threshold": None,
    }

    if show_current:
        result["current"] = current_value_for_metric_type(metric_type=metric_type, user=user, at=at)

    if show_chart or show_max or show_min or show_avg or show_time_in_range:
        range_start, range_end, bucket = resolve_named_range(
            timeframe, at=at, custom_start=custom_start, custom_end=custom_end
        )
        points = points_for_metric_type(
            metric_type=metric_type, user=user, range_start=range_start, range_end=range_end
        )
        if show_chart:
            result["points"] = [
                {"timestamp": p.recorded_at.isoformat(), "value": p.value}
                for p in sorted(points, key=lambda p: p.recorded_at)
            ]
            result["timeframe_unit"] = bucket.unit.value
        if show_max or show_min or show_avg:
            summary = summarize(points)
            result["max"] = summary.max
            result["min"] = summary.min
            result["avg"] = summary.avg
        # The threshold also feeds the chart's red bound lines, so it's
        # fetched whenever either show_chart or show_time_in_range needs it
        # — one query, two consumers, same "resolve once" rule as everything
        # else here.
        if show_chart or show_time_in_range:
            threshold = metric_threshold_get_for_user(user=user, metric_type_id=metric_type.id)
            if threshold is not None:
                result["threshold"] = {
                    "lower_bound": threshold.lower_bound,
                    "upper_bound": threshold.upper_bound,
                }
                if show_time_in_range:
                    result["time_in_range_percent"] = time_in_range_percent(
                        points,
                        lower_bound=threshold.lower_bound,
                        upper_bound=threshold.upper_bound,
                    )

    result["period_changes"] = period_changes_for_metric_type(
        metric_type=metric_type, user=user, at=at
    )
    return result


def _dashboard_element_dict(element: DashboardElement, stats: dict) -> dict:
    # Reuse MetricTypeSerializer rather than hand-building this dict, so a
    # field added to MetricType's API shape later doesn't have to be
    # remembered here too — a prior manual dict drifted out of sync with the
    # frontend's metricTypeSchema and silently broke every consumer of the
    # old favorites endpoint's shared query key.
    from .serializers import MetricTypeSerializer

    return {
        "id": element.id,
        "order": element.order,
        "metric_type": MetricTypeSerializer(element.metric_type).data,
        "show_chart": element.show_chart,
        "show_current": element.show_current,
        "show_max": element.show_max,
        "show_min": element.show_min,
        "show_avg": element.show_avg,
        "show_time_in_range": element.show_time_in_range,
        "timeframe": element.timeframe,
        "custom_range_start": element.custom_range_start,
        "custom_range_end": element.custom_range_end,
        **stats,
    }


def dashboard_element_data(*, element: DashboardElement, at: datetime) -> dict:
    stats = dashboard_element_stats(
        metric_type=element.metric_type,
        user=element.user,
        show_chart=element.show_chart,
        show_current=element.show_current,
        show_max=element.show_max,
        show_min=element.show_min,
        show_avg=element.show_avg,
        show_time_in_range=element.show_time_in_range,
        timeframe=element.timeframe,
        custom_start=element.custom_range_start,
        custom_end=element.custom_range_end,
        at=at,
    )
    return _dashboard_element_dict(element, stats)


def dashboard_elements_data_for_user(*, user, at: datetime) -> list[dict]:
    """Every configured dashboard element for `user`, each with its resolved
    stats — one response for the whole dashboard, not one `/aggregate/`-style
    request per block."""
    return [
        dashboard_element_data(element=element, at=at)
        for element in dashboard_element_list_for_user(user=user)
    ]


def metric_import_settings_get_for_user(
    *, user, metric_type_id: int
) -> MetricImportSettings | None:
    return MetricImportSettings.objects.filter(user=user, metric_type_id=metric_type_id).first()


def formula_definition_list() -> QuerySet[FormulaDefinition]:
    return FormulaDefinition.objects.select_related("computed_metric_type")


def formula_definition_get(*, formula_definition_id: int) -> FormulaDefinition | None:
    return FormulaDefinition.objects.filter(id=formula_definition_id).first()


def dashboard_summary_for_user(*, user) -> dict:
    """Everything the dashboard's KPI row + chart cards need, gathered in one
    call — same "aggregate once, derive many stats" rule as
    `points_for_metric_type`/the `/aggregate/` endpoint. Entry/threshold
    counts and the breakdowns are scoped to `user` (dashboards are personal,
    admins included — same as `/aggregate/`); the metric-type count is the
    shared catalog size, visible to everyone.
    """
    entries = metric_entry_list_for_user(user=user)

    by_metric_type = (
        entries.values("metric_type__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    trend_start = (timezone.now() - relativedelta(months=DASHBOARD_TREND_MONTHS - 1)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    by_month = (
        entries.filter(recorded_at__gte=trend_start)
        .annotate(month=TruncMonth("recorded_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    return {
        "metric_type_count": MetricType.objects.count(),
        "entry_count": entries.count(),
        "threshold_count": metric_threshold_list_for_user(user=user).count(),
        "entries_by_metric_type": [
            {"metric_type_name": row["metric_type__name"], "count": row["count"]}
            for row in by_metric_type
        ],
        "entries_by_month": [
            {"month": row["month"].strftime("%Y-%m"), "count": row["count"]} for row in by_month
        ],
    }
