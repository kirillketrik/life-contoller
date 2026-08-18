from datetime import datetime, timezone

import pytest
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import MetricEntry, MetricThreshold, MetricType

pytestmark = pytest.mark.django_db


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestDashboardSummaryEndpoint:
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/dashboard-summary/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_counts_are_scoped_to_requesting_user(
        self, authenticated_client, regular_user, other_user, number_metric_type
    ):
        baker.make(MetricEntry, metric_type=number_metric_type, owner=regular_user, value=1)
        baker.make(MetricEntry, metric_type=number_metric_type, owner=other_user, value=2)
        baker.make(MetricThreshold, user=regular_user, metric_type=number_metric_type, lower_bound=0)

        response = authenticated_client.get("/api/dashboard-summary/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["metric_type_count"] == MetricType.objects.count()
        assert response.data["entry_count"] == 1
        assert response.data["threshold_count"] == 1

    def test_entries_by_metric_type_breakdown(self, authenticated_client, regular_user, db):
        weight = baker.make(MetricType, name="Weight")
        water = baker.make(MetricType, name="Water")
        baker.make(MetricEntry, metric_type=weight, owner=regular_user, value=1, _quantity=2)
        baker.make(MetricEntry, metric_type=water, owner=regular_user, value=1)

        response = authenticated_client.get("/api/dashboard-summary/")

        breakdown = {row["metric_type_name"]: row["count"] for row in response.data["entries_by_metric_type"]}
        assert breakdown == {"Weight": 2, "Water": 1}

    def test_entries_by_month_excludes_old_entries(self, authenticated_client, regular_user, number_metric_type):
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=1,
            recorded_at=dt(2020, 1, 1),
        )

        response = authenticated_client.get("/api/dashboard-summary/")

        assert response.data["entries_by_month"] == []
