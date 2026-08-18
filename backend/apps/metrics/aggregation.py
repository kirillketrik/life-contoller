"""Generic timeframe aggregation over (timestamp, numeric value) points.

Deliberately works on plain `DataPoint`s rather than a `MetricEntry`
queryset: the same bucketing/summary/time-in-range logic serves both stored
entries and on-the-fly computed series from `apps.metrics.formulas` (BMI,
etc.) — neither cares where a point came from, only that it has a timestamp
and a numeric value. Views build the `DataPoint` list from whichever source
applies (see `apps.metrics.selectors.points_for_metric_type`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
