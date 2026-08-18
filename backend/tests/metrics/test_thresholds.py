import pytest
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import MetricThreshold

pytestmark = pytest.mark.django_db


class TestMetricThresholdPermissions:
    def test_anonymous_cannot_list(self, api_client):
        response = api_client.get("/api/metric-thresholds/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_create_own_threshold(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            "/api/metric-thresholds/",
            {"metric_type": number_metric_type.id, "lower_bound": 70, "upper_bound": 100},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["upper_bound"] == 100

    def test_user_only_sees_own_thresholds(
        self, authenticated_client, number_metric_type, regular_user, other_user
    ):
        baker.make(MetricThreshold, user=other_user, metric_type=number_metric_type, upper_bound=100)
        mine = baker.make(MetricThreshold, user=regular_user, metric_type=number_metric_type, upper_bound=90)
        response = authenticated_client.get("/api/metric-thresholds/")
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {mine.id}

    def test_user_cannot_edit_another_users_threshold(
        self, authenticated_client, number_metric_type, other_user
    ):
        theirs = baker.make(MetricThreshold, user=other_user, metric_type=number_metric_type, upper_bound=100)
        response = authenticated_client.patch(
            f"/api/metric-thresholds/{theirs.id}/", {"upper_bound": 50}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_requires_at_least_one_bound(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            "/api/metric-thresholds/", {"metric_type": number_metric_type.id}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_lower_bound_must_not_exceed_upper_bound(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            "/api/metric-thresholds/",
            {"metric_type": number_metric_type.id, "lower_bound": 100, "upper_bound": 50},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_only_upper_bound_is_allowed(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            "/api/metric-thresholds/", {"metric_type": number_metric_type.id, "upper_bound": 140}
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["lower_bound"] is None

    def test_duplicate_threshold_for_same_metric_type_rejected(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(MetricThreshold, user=regular_user, metric_type=number_metric_type, upper_bound=100)
        response = authenticated_client.post(
            "/api/metric-thresholds/", {"metric_type": number_metric_type.id, "upper_bound": 90}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
