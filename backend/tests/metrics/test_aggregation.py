from datetime import datetime, timedelta, timezone

import pytest
from dateutil.relativedelta import relativedelta

from apps.metrics.aggregation import (
    DataPoint,
    Timeframe,
    TimeframeUnit,
    bucketize,
    period_percent_changes,
    summarize,
    time_in_range_percent,
)


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestBucketizeFixedDurationUnits:
    def test_groups_points_within_the_same_hour_bucket(self):
        range_start = dt(2026, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2026, 1, 1, 0, 5), 10),
            DataPoint(dt(2026, 1, 1, 0, 45), 20),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.HOUR, 1), range_start)
        assert len(buckets) == 1
        assert buckets[0].bucket_start == range_start
        assert buckets[0].open == 10
        assert buckets[0].close == 20
        assert buckets[0].high == 20
        assert buckets[0].low == 10
        assert buckets[0].count == 2

    def test_point_exactly_on_a_boundary_starts_the_next_bucket(self):
        range_start = dt(2026, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2026, 1, 1, 0, 59, 59), 1),
            DataPoint(dt(2026, 1, 1, 1, 0, 0), 2),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.HOUR, 1), range_start)
        assert len(buckets) == 2
        assert buckets[0].bucket_start == dt(2026, 1, 1, 0, 0)
        assert buckets[1].bucket_start == dt(2026, 1, 1, 1, 0)

    def test_n_unit_buckets_group_multiple_units_together(self):
        range_start = dt(2026, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2026, 1, 1, 0, 0), 1),
            DataPoint(dt(2026, 1, 1, 3, 59), 2),
            DataPoint(dt(2026, 1, 1, 4, 0), 3),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.HOUR, 4), range_start)
        assert len(buckets) == 2
        assert buckets[0].count == 2
        assert buckets[1].count == 1

    def test_week_buckets_are_anchored_to_range_start(self):
        range_start = dt(2026, 1, 5, 0, 0)  # a Monday
        points = [
            DataPoint(dt(2026, 1, 5, 12, 0), 1),
            DataPoint(dt(2026, 1, 11, 23, 59), 2),
            DataPoint(dt(2026, 1, 12, 0, 0), 3),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.WEEK, 1), range_start)
        assert len(buckets) == 2
        assert buckets[0].bucket_start == range_start
        assert buckets[1].bucket_start == dt(2026, 1, 12, 0, 0)

    def test_minute_buckets(self):
        range_start = dt(2026, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2026, 1, 1, 0, 0, 10), 1),
            DataPoint(dt(2026, 1, 1, 0, 14, 59), 2),
            DataPoint(dt(2026, 1, 1, 0, 15, 0), 3),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.MINUTE, 15), range_start)
        assert len(buckets) == 2
        assert buckets[0].count == 2
        assert buckets[1].count == 1


class TestBucketizeCalendarUnits:
    def test_month_buckets_handle_variable_month_length(self):
        range_start = dt(2026, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2026, 1, 15), 1),
            DataPoint(dt(2026, 1, 31), 2),
            DataPoint(dt(2026, 2, 1), 3),
            DataPoint(dt(2026, 2, 28), 4),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.MONTH, 1), range_start)
        assert [b.bucket_start for b in buckets] == [dt(2026, 1, 1), dt(2026, 2, 1)]
        assert buckets[0].count == 2
        assert buckets[1].count == 2

    def test_n_month_buckets_group_quarters(self):
        range_start = dt(2026, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2026, 1, 10), 1),
            DataPoint(dt(2026, 3, 20), 2),
            DataPoint(dt(2026, 4, 1), 3),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.MONTH, 3), range_start)
        assert len(buckets) == 2
        assert buckets[0].bucket_start == dt(2026, 1, 1)
        assert buckets[0].count == 2
        assert buckets[1].bucket_start == dt(2026, 4, 1)
        assert buckets[1].count == 1

    def test_year_buckets(self):
        range_start = dt(2024, 6, 1, 0, 0)
        points = [
            DataPoint(dt(2024, 12, 31), 1),
            DataPoint(dt(2025, 1, 1), 2),
            DataPoint(dt(2026, 6, 1), 3),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.YEAR, 1), range_start)
        assert [b.bucket_start for b in buckets] == [dt(2024, 1, 1), dt(2025, 1, 1), dt(2026, 1, 1)]

    def test_n_year_buckets(self):
        range_start = dt(2020, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2020, 5, 1), 1),
            DataPoint(dt(2021, 5, 1), 2),
            DataPoint(dt(2022, 5, 1), 3),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.YEAR, 2), range_start)
        assert len(buckets) == 2
        assert buckets[0].count == 2
        assert buckets[1].count == 1


class TestBucketizeSparseData:
    def test_one_point_per_day_yields_flat_ohlc_buckets(self):
        range_start = dt(2026, 1, 1, 0, 0)
        points = [
            DataPoint(dt(2026, 1, 1, 8, 0), 70.0),
            DataPoint(dt(2026, 1, 3, 8, 0), 70.5),
        ]
        buckets = bucketize(points, Timeframe(TimeframeUnit.DAY, 1), range_start)
        assert len(buckets) == 2  # day 2 has no data — no empty bucket emitted
        for bucket in buckets:
            assert bucket.open == bucket.high == bucket.low == bucket.close
            assert bucket.count == 1

    def test_no_points_yields_no_buckets(self):
        assert bucketize([], Timeframe(TimeframeUnit.DAY, 1), dt(2026, 1, 1)) == []


class TestSummarize:
    def test_empty_points(self):
        summary = summarize([])
        assert summary.min is None
        assert summary.max is None
        assert summary.avg is None
        assert summary.count == 0

    def test_min_max_avg(self):
        points = [DataPoint(dt(2026, 1, 1), v) for v in (10, 20, 30)]
        summary = summarize(points)
        assert summary.min == 10
        assert summary.max == 30
        assert summary.avg == 20
        assert summary.count == 3


class TestTimeInRangePercent:
    def test_no_thresholds_configured_returns_none(self):
        points = [DataPoint(dt(2026, 1, 1), 100)]
        assert time_in_range_percent(points, lower_bound=None, upper_bound=None) is None

    def test_no_points_returns_none(self):
        assert time_in_range_percent([], lower_bound=0, upper_bound=10) is None

    def test_counts_inclusive_of_both_bounds(self):
        points = [DataPoint(dt(2026, 1, 1), v) for v in (70, 80, 90, 100)]
        result = time_in_range_percent(points, lower_bound=80, upper_bound=90)
        assert result == 50.0

    def test_lower_bound_only(self):
        points = [DataPoint(dt(2026, 1, 1), v) for v in (5, 10, 15)]
        result = time_in_range_percent(points, lower_bound=10, upper_bound=None)
        assert result == pytest.approx(2 / 3 * 100)

    def test_upper_bound_only(self):
        points = [DataPoint(dt(2026, 1, 1), v) for v in (5, 10, 15)]
        result = time_in_range_percent(points, lower_bound=None, upper_bound=10)
        assert result == pytest.approx(2 / 3 * 100)


class TestPeriodPercentChanges:
    PERIODS = [("24h", timedelta(hours=24)), ("7d", timedelta(days=7))]

    def test_computes_percent_change_against_lookback(self):
        at = dt(2026, 1, 8, 12)
        points = [
            DataPoint(dt(2026, 1, 1, 12), 100),  # 7d ago
            DataPoint(dt(2026, 1, 7, 12), 120),  # 24h ago
            DataPoint(dt(2026, 1, 8, 12), 150),  # current
        ]
        result = period_percent_changes(points, at=at, periods=self.PERIODS)
        assert result["24h"] == pytest.approx((150 - 120) / 120 * 100)
        assert result["7d"] == pytest.approx((150 - 100) / 100 * 100)

    def test_uses_latest_point_at_or_before_the_lookback_target(self):
        at = dt(2026, 1, 8, 12)
        points = [
            DataPoint(dt(2026, 1, 6, 0), 100),  # latest point <= 24h-ago target
            DataPoint(dt(2026, 1, 7, 18), 200),  # after the 24h-ago target, ignored for it
            DataPoint(dt(2026, 1, 8, 12), 300),
        ]
        result = period_percent_changes(points, at=at, periods=[("24h", timedelta(hours=24))])
        assert result["24h"] == pytest.approx((300 - 100) / 100 * 100)

    def test_no_data_before_lookback_target_is_none(self):
        at = dt(2026, 1, 8, 12)
        points = [DataPoint(dt(2026, 1, 8, 0), 100)]
        result = period_percent_changes(points, at=at, periods=self.PERIODS)
        assert result["24h"] is None  # only point is after the 24h-ago target
        assert result["7d"] is None

    def test_no_current_value_is_none(self):
        at = dt(2026, 1, 8, 12)
        points = []
        result = period_percent_changes(points, at=at, periods=self.PERIODS)
        assert result == {"24h": None, "7d": None}

    def test_zero_past_value_is_none_not_division_error(self):
        at = dt(2026, 1, 8, 12)
        points = [DataPoint(dt(2026, 1, 1, 12), 0), DataPoint(dt(2026, 1, 8, 12), 50)]
        result = period_percent_changes(points, at=at, periods=[("7d", timedelta(days=7))])
        assert result["7d"] is None

    def test_supports_relativedelta_periods(self):
        at = dt(2026, 4, 1, 0)
        points = [DataPoint(dt(2026, 1, 1, 0), 50), DataPoint(dt(2026, 4, 1, 0), 75)]
        result = period_percent_changes(
            points, at=at, periods=[("3m", relativedelta(months=3))]
        )
        assert result["3m"] == pytest.approx(50.0)
