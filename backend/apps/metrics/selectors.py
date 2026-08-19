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
    RangeSummary,
    Timeframe,
    TimeframeUnit,
    bucketize,
    period_percent_changes,
    summarize,
)
from .formula_engine import computed_series
from .models import (
    FavoriteMetric,
    FormulaDefinition,
    MetricEntry,
    MetricImportSettings,
    MetricThreshold,
    MetricType,
    ValueType,
)

DASHBOARD_TREND_MONTHS = 12
FAVORITE_CHART_RANGE_DAYS = 30
FAVORITE_CHART_TIMEFRAME = Timeframe(unit=TimeframeUnit.DAY, count=1)

# The KPI badges shown next to a metric's name (dashboard favorite card and
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


def metric_type_list() -> QuerySet[MetricType]:
    """All metric types are shared, readable definitions — visible to any
    authenticated user."""
    return MetricType.objects.all()


def metric_type_get(*, metric_type_id: int) -> MetricType | None:
    return MetricType.objects.filter(id=metric_type_id).first()


def metric_entry_list_for_user(*, user, metric_type_id: int | None = None) -> QuerySet[MetricEntry]:
    """Entries owned by `user` only — ownership-based like `MetricThreshold`,
    with no admin override. Logging entries is a personal action; an admin
    account is not entitled to see or manage another user's readings just by
    virtue of the role, same as thresholds and favorites. Optionally narrowed
    to a single `MetricType`."""
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


def favorite_metric_list_for_user(*, user) -> QuerySet[FavoriteMetric]:
    return FavoriteMetric.objects.filter(user=user).select_related("metric_type")


def favorites_chart_data_for_user(*, user) -> list[dict]:
    """Every favorited metric type for `user`, each with a pre-bucketed recent
    series — so the dashboard's favorites section renders every card from
    this one response instead of one `/aggregate/` request per card.

    Mirrors `points_for_metric_type`/`bucketize`/`summarize` (used by the
    `/aggregate/` action), just with a fixed recent-range window instead of a
    caller-supplied timeframe. Non-chartable metric types (favorited is
    normally prevented by the UI, but the API doesn't enforce it — see
    `apps.metrics.views`) degrade to an empty series rather than erroring.
    """
    range_end = timezone.now()
    range_start = range_end - timedelta(days=FAVORITE_CHART_RANGE_DAYS)

    result = []
    for favorite in favorite_metric_list_for_user(user=user):
        metric_type = favorite.metric_type
        chartable = metric_type.is_computed or metric_type.value_type == ValueType.NUMBER
        if chartable:
            points = points_for_metric_type(
                metric_type=metric_type, user=user, range_start=range_start, range_end=range_end
            )
            buckets = bucketize(points, FAVORITE_CHART_TIMEFRAME, range_start)
            summary = summarize(points)
            period_changes = period_changes_for_metric_type(
                metric_type=metric_type, user=user, at=range_end
            )
        else:
            buckets = []
            summary = RangeSummary(min=None, max=None, avg=None, count=0)
            period_changes = {label: None for label, _ in PERIOD_CHANGE_SPECS}

        # Reuse MetricTypeSerializer rather than hand-building this dict, so a
        # field added to MetricType's API shape later (is_singleton, choices)
        # doesn't have to be remembered here too — a prior manual dict drifted
        # out of sync with the frontend's metricTypeSchema and silently broke
        # every consumer of this endpoint's shared query key (favorite
        # toggling and the dashboard favorites section alike).
        from .serializers import MetricTypeSerializer

        result.append(
            {
                "id": favorite.id,
                "order": favorite.order,
                "metric_type": MetricTypeSerializer(metric_type).data,
                "timeframe_unit": FAVORITE_CHART_TIMEFRAME.unit.value,
                "buckets": [
                    {
                        "bucket_start": bucket.bucket_start.isoformat(),
                        "open": bucket.open,
                        "high": bucket.high,
                        "low": bucket.low,
                        "close": bucket.close,
                        "count": bucket.count,
                    }
                    for bucket in buckets
                ],
                "summary": {
                    "min": summary.min,
                    "max": summary.max,
                    "avg": summary.avg,
                    "count": summary.count,
                },
                "period_changes": period_changes,
            }
        )
    return result


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
