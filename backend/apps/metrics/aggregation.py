"""Generic timeframe aggregation over (timestamp, numeric value) points.

Deliberately works on plain `DataPoint`s rather than a `MetricEntry`
queryset: the same bucketing/summary/time-in-range logic serves both stored
entries and on-the-fly computed series from `apps.metrics.formula_engine`
(BMI, etc.) — neither cares where a point came from, only that it has a timestamp
and a numeric value. Views build the `DataPoint` list from whichever source
applies (see `apps.metrics.selectors.points_for_metric_type`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum

from dateutil.relativedelta import relativedelta


class TimeframeUnit(str, Enum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


_FIXED_DURATION_SECONDS = {
    TimeframeUnit.MINUTE: 60,
    TimeframeUnit.HOUR: 3600,
    TimeframeUnit.DAY: 86400,
    TimeframeUnit.WEEK: 604800,
}


@dataclass(frozen=True)
class Timeframe:
    """A bucket width: N units, e.g. Timeframe(TimeframeUnit.HOUR, 4) = "4 hours"."""

    unit: TimeframeUnit
    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("timeframe count must be >= 1")


@dataclass(frozen=True)
class DataPoint:
    recorded_at: datetime
    value: float


@dataclass(frozen=True)
class OHLCBucket:
    bucket_start: datetime
    open: float
    high: float
    low: float
    close: float
    count: int


@dataclass(frozen=True)
class RangeSummary:
    min: float | None
    max: float | None
    avg: float | None
    count: int


def _bucket_start(dt: datetime, timeframe: Timeframe, anchor: datetime) -> datetime:
    """The start of the bucket `dt` falls into, for buckets of `timeframe`
    anchored at `anchor` (the start of the requested date range).

    Minute/hour/day/week buckets are fixed-duration and anchored to `anchor`
    so bucket boundaries are stable regardless of calendar quirks. Month/year
    buckets are calendar-aligned instead (a "month" isn't a fixed duration)
    and grouped into N-unit chunks starting from `anchor`'s month/year.
    """
    unit = timeframe.unit
    n = timeframe.count
    if unit in _FIXED_DURATION_SECONDS:
        bucket_seconds = _FIXED_DURATION_SECONDS[unit] * n
        elapsed = (dt - anchor).total_seconds()
        bucket_index = int(elapsed // bucket_seconds)
        return anchor + timedelta(seconds=bucket_index * bucket_seconds)

    if unit is TimeframeUnit.MONTH:
        anchor_month_start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        months_elapsed = (dt.year - anchor.year) * 12 + (dt.month - anchor.month)
        bucket_index = months_elapsed // n
        return anchor_month_start + relativedelta(months=bucket_index * n)

    if unit is TimeframeUnit.YEAR:
        anchor_year_start = anchor.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        years_elapsed = dt.year - anchor.year
        bucket_index = years_elapsed // n
        return anchor_year_start + relativedelta(years=bucket_index * n)

    raise ValueError(f"Unsupported timeframe unit: {unit}")


def bucketize(
    points: list[DataPoint], timeframe: Timeframe, range_start: datetime
) -> list[OHLCBucket]:
    """Group points into OHLC buckets. Buckets with no points are omitted
    (sparse data just yields fewer buckets, not zero-filled ones)."""
    grouped: dict[datetime, list[DataPoint]] = {}
    for point in sorted(points, key=lambda p: p.recorded_at):
        start = _bucket_start(point.recorded_at, timeframe, range_start)
        grouped.setdefault(start, []).append(point)

    buckets = []
    for start in sorted(grouped):
        bucket_points = grouped[start]  # chronological, since we inserted in sorted order
        values = [p.value for p in bucket_points]
        buckets.append(
            OHLCBucket(
                bucket_start=start,
                open=bucket_points[0].value,
                close=bucket_points[-1].value,
                high=max(values),
                low=min(values),
                count=len(bucket_points),
            )
        )
    return buckets


def summarize(points: list[DataPoint]) -> RangeSummary:
    """Min/max/avg across all points in the range (not bucketed)."""
    if not points:
        return RangeSummary(min=None, max=None, avg=None, count=0)
    values = [p.value for p in points]
    return RangeSummary(
        min=min(values), max=max(values), avg=sum(values) / len(values), count=len(values)
    )


def time_in_range_percent(
    points: list[DataPoint], *, lower_bound: float | None, upper_bound: float | None
) -> float | None:
    """Percentage of points within [lower_bound, upper_bound] (inclusive of
    whichever bound is set), counted per-entry.

    Deliberately entry-count-based, not time-weighted/interpolated, per
    current product scope — kept as its own function so a time-weighted mode
    can be added later (e.g. `time_in_range_percent_weighted`) without
    changing this function's contract or its callers.
    """
    if lower_bound is None and upper_bound is None:
        return None
    if not points:
        return None
    in_range = sum(
        1
        for point in points
        if (lower_bound is None or point.value >= lower_bound)
        and (upper_bound is None or point.value <= upper_bound)
    )
    return (in_range / len(points)) * 100


@dataclass(frozen=True)
class NamedRangePreset:
    """One entry of the shared timeframe-preset vocabulary used both by the
    ad hoc `/aggregate/` query params (built from these on the frontend, see
    `lib/metric-range-presets.ts`'s `RANGE_PRESETS`) and by a persisted
    `DashboardElement.timeframe` choice — one representation, not two."""

    length: timedelta | relativedelta
    bucket: Timeframe


NAMED_RANGE_PRESETS: dict[str, NamedRangePreset] = {
    "7d": NamedRangePreset(timedelta(days=7), Timeframe(TimeframeUnit.HOUR, 6)),
    "30d": NamedRangePreset(timedelta(days=30), Timeframe(TimeframeUnit.DAY, 1)),
    "90d": NamedRangePreset(timedelta(days=90), Timeframe(TimeframeUnit.DAY, 1)),
    "1y": NamedRangePreset(relativedelta(years=1), Timeframe(TimeframeUnit.WEEK, 1)),
    "3y": NamedRangePreset(relativedelta(years=3), Timeframe(TimeframeUnit.MONTH, 1)),
    # Same "100 years back" stand-in for "unbounded" as PERIOD_CHANGE_LOOKBACK
    # and the frontend's own "Всё время" preset — not truly unbounded.
    "all": NamedRangePreset(relativedelta(years=100), Timeframe(TimeframeUnit.MONTH, 1)),
}


def _bucket_for_span_days(span_days: float) -> Timeframe:
    """Bucket granularity for a custom range, chosen by span using the same
    breakpoints `NAMED_RANGE_PRESETS` already encodes for the fixed presets."""
    if span_days <= 7:
        return Timeframe(TimeframeUnit.HOUR, 6)
    if span_days <= 90:
        return Timeframe(TimeframeUnit.DAY, 1)
    if span_days <= 365:
        return Timeframe(TimeframeUnit.WEEK, 1)
    return Timeframe(TimeframeUnit.MONTH, 1)


def resolve_named_range(
    key: str,
    *,
    at: datetime,
    custom_start: date | None = None,
    custom_end: date | None = None,
) -> tuple[datetime, datetime, Timeframe]:
    """Resolves a named timeframe key (a `NAMED_RANGE_PRESETS` key, or
    `"custom"`) into a concrete `(range_start, range_end, bucket)` tuple for
    a `DashboardElement`'s stored `timeframe` — the same resolved range then
    feeds both the chart buckets and the max/min/avg calculation, per that
    model's contract."""
    if key == "custom":
        if custom_start is None or custom_end is None:
            raise ValueError("custom_start and custom_end are required for a custom range.")
        range_start = datetime.combine(custom_start, time.min, tzinfo=at.tzinfo)
        range_end = datetime.combine(custom_end, time.max, tzinfo=at.tzinfo)
        span_days = (range_end - range_start).total_seconds() / 86400
        return range_start, range_end, _bucket_for_span_days(span_days)

    preset = NAMED_RANGE_PRESETS.get(key)
    if preset is None:
        raise ValueError(f"Unknown named range: {key}")
    return at - preset.length, at, preset.bucket


def period_percent_changes(
    points: list[DataPoint],
    *,
    at: datetime,
    periods: list[tuple[str, timedelta | relativedelta]],
) -> dict[str, float | None]:
    """% change between the latest value at/before `at` and the latest value
    at/before each `at - period` lookback, keyed by label (e.g. "24h").

    `None` for a given period when either side has no data at all — most
    commonly because the metric didn't exist that far back yet — rather than
    guessing or substituting a default, same "never fabricate a missing
    value" rule as the rest of this module.
    """
    sorted_points = sorted(points, key=lambda p: p.recorded_at)

    def value_at_or_before(target: datetime) -> float | None:
        value = None
        for point in sorted_points:
            if point.recorded_at > target:
                break
            value = point.value
        return value

    current = value_at_or_before(at)
    changes: dict[str, float | None] = {}
    for label, period in periods:
        past = value_at_or_before(at - period)
        if current is None or past is None or past == 0:
            changes[label] = None
        else:
            changes[label] = (current - past) / abs(past) * 100
    return changes
