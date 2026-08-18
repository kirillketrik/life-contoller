from datetime import UTC, datetime

import pytest
from model_bakery import baker
from rest_framework import status

from apps.metrics.formula_engine import builtins
from apps.metrics.models import (
    FormulaDefinition,
    MetricEntry,
    MetricThreshold,
    MetricType,
    ValueType,
)

pytestmark = pytest.mark.django_db


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


class TestAggregateEndpoint:
    def test_requires_authentication(self, api_client, number_metric_type):
        response = api_client.get(
            f"/api/metric-types/{number_metric_type.id}/aggregate/",
            {"timeframe_unit": "day", "timeframe_count": 1},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_returns_buckets_and_summary(self, authenticated_client, number_metric_type, regular_user):
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=70,
            recorded_at=dt(2026, 1, 1, 8),
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=72,
            recorded_at=dt(2026, 1, 1, 20),
        )
        response = authenticated_client.get(
            f"/api/metric-types/{number_metric_type.id}/aggregate/",
            {
                "timeframe_unit": "day",
                "timeframe_count": 1,
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["buckets"]) == 1
        bucket = response.data["buckets"][0]
        assert bucket["open"] == 70
        assert bucket["close"] == 72
        assert bucket["high"] == 72
        assert bucket["low"] == 70
        assert response.data["summary"]["min"] == 70
        assert response.data["summary"]["max"] == 72
        assert response.data["summary"]["avg"] == 71
        assert response.data["time_in_range_percent"] is None

    def test_only_returns_requesting_users_data(
        self, authenticated_client, number_metric_type, regular_user, other_user
    ):
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=other_user,
            value=999,
            recorded_at=dt(2026, 1, 1, 8),
        )
        response = authenticated_client.get(
            f"/api/metric-types/{number_metric_type.id}/aggregate/",
            {
                "timeframe_unit": "day",
                "timeframe_count": 1,
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
        )
        assert response.data["buckets"] == []
        assert response.data["summary"]["count"] == 0

    def test_time_in_range_uses_configured_threshold(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(MetricThreshold, user=regular_user, metric_type=number_metric_type, lower_bound=70, upper_bound=100)
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=60,
            recorded_at=dt(2026, 1, 1, 8),
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=80,
            recorded_at=dt(2026, 1, 1, 9),
        )
        response = authenticated_client.get(
            f"/api/metric-types/{number_metric_type.id}/aggregate/",
            {
                "timeframe_unit": "day",
                "timeframe_count": 1,
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
        )
        assert response.data["time_in_range_percent"] == 50.0

    def test_rejects_non_number_non_computed_metric_type(self, authenticated_client, db):
        text_type = baker.make(MetricType, value_type=ValueType.TEXT)
        response = authenticated_client.get(
            f"/api/metric-types/{text_type.id}/aggregate/",
            {"timeframe_unit": "day", "timeframe_count": 1},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_timeframe_unit_is_rejected(self, authenticated_client, number_metric_type):
        response = authenticated_client.get(
            f"/api/metric-types/{number_metric_type.id}/aggregate/",
            {"timeframe_unit": "fortnight", "timeframe_count": 1},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_defaults_to_last_30_days_when_no_range_given(
        self, authenticated_client, number_metric_type, regular_user
    ):
        response = authenticated_client.get(
            f"/api/metric-types/{number_metric_type.id}/aggregate/",
            {"timeframe_unit": "day", "timeframe_count": 1},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_computed_metric_type_end_to_end(self, authenticated_client, regular_user, db):
        weight = baker.make(MetricType, value_type=ValueType.NUMBER, unit="kg")
        height = baker.make(MetricType, value_type=ValueType.NUMBER, unit="cm")
        bmi = baker.make(MetricType, value_type=ValueType.NUMBER, is_computed=True)
        baker.make(
            FormulaDefinition,
            computed_metric_type=bmi,
            expression=builtins.build_bmi(weight_kg_id=weight.id, height_cm_id=height.id),
        )
        baker.make(
            MetricEntry, metric_type=weight, owner=regular_user, value=70, recorded_at=dt(2026, 1, 1, 8)
        )
        baker.make(
            MetricEntry, metric_type=height, owner=regular_user, value=175, recorded_at=dt(2026, 1, 1, 8)
        )

        response = authenticated_client.get(
            f"/api/metric-types/{bmi.id}/aggregate/",
            {
                "timeframe_unit": "day",
                "timeframe_count": 1,
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["buckets"]) == 1
        assert response.data["buckets"][0]["close"] == pytest.approx(70 / (1.75**2))
