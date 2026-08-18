from datetime import timedelta

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import FavoriteMetric

pytestmark = pytest.mark.django_db


def _favorite_url(metric_type) -> str:
    return f"/api/metric-types/{metric_type.id}/favorite/"


class TestFavoriteMetricToggle:
    def test_anonymous_cannot_favorite(self, api_client, number_metric_type):
        response = api_client.post(_favorite_url(number_metric_type))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_list_favorites(self, api_client):
        response = api_client.get("/api/metric-types/favorites/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_favorite(
        self, authenticated_client, number_metric_type, regular_user
    ):
        response = authenticated_client.post(_favorite_url(number_metric_type))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert FavoriteMetric.objects.filter(
            user=regular_user, metric_type=number_metric_type
        ).exists()

    def test_favoriting_twice_is_idempotent(
        self, authenticated_client, number_metric_type, regular_user
    ):
        authenticated_client.post(_favorite_url(number_metric_type))
        response = authenticated_client.post(_favorite_url(number_metric_type))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        existing = FavoriteMetric.objects.filter(user=regular_user, metric_type=number_metric_type)
        assert existing.count() == 1

    def test_unfavorite_removes_it(self, authenticated_client, number_metric_type, regular_user):
        baker.make(FavoriteMetric, user=regular_user, metric_type=number_metric_type)
        response = authenticated_client.delete(_favorite_url(number_metric_type))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not FavoriteMetric.objects.filter(
            user=regular_user, metric_type=number_metric_type
        ).exists()

    def test_unfavoriting_when_not_favorited_is_a_noop(
        self, authenticated_client, number_metric_type
    ):
        response = authenticated_client.delete(_favorite_url(number_metric_type))
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_favoriting_unknown_metric_type_404s(self, authenticated_client):
        response = authenticated_client.post("/api/metric-types/999999/favorite/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestFavoriteMetricList:
    def test_favorites_are_scoped_per_user(
        self, authenticated_client, number_metric_type, regular_user, other_user
    ):
        baker.make(FavoriteMetric, user=other_user, metric_type=number_metric_type)
        mine = baker.make(FavoriteMetric, user=regular_user, metric_type=number_metric_type)

        response = authenticated_client.get("/api/metric-types/favorites/")
        assert response.status_code == status.HTTP_200_OK
        returned_ids = {item["id"] for item in response.data}
        assert returned_ids == {mine.id}

    def test_favorite_includes_recent_entries_as_buckets(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(FavoriteMetric, user=regular_user, metric_type=number_metric_type)
        baker.make(
            "metrics.MetricEntry",
            metric_type=number_metric_type,
            owner=regular_user,
            value=72,
            recorded_at=timezone.now() - timedelta(days=1),
        )

        response = authenticated_client.get("/api/metric-types/favorites/")
        assert response.status_code == status.HTTP_200_OK
        [favorite] = response.data
        assert favorite["metric_type"]["id"] == number_metric_type.id
        assert favorite["summary"]["count"] == 1
        assert len(favorite["buckets"]) == 1

    def test_favorite_of_other_users_entries_not_included(
        self, authenticated_client, number_metric_type, regular_user, other_user
    ):
        baker.make(FavoriteMetric, user=regular_user, metric_type=number_metric_type)
        baker.make(
            "metrics.MetricEntry",
            metric_type=number_metric_type,
            owner=other_user,
            value=99,
            recorded_at=timezone.now(),
        )

        response = authenticated_client.get("/api/metric-types/favorites/")
        [favorite] = response.data
        assert favorite["summary"]["count"] == 0


class TestFavoriteMetricReorder:
    def test_reorder_persists_order(self, authenticated_client, regular_user):
        mt_a = baker.make("metrics.MetricType", value_type="number")
        mt_b = baker.make("metrics.MetricType", value_type="number")
        fav_a = baker.make(FavoriteMetric, user=regular_user, metric_type=mt_a, order=0)
        fav_b = baker.make(FavoriteMetric, user=regular_user, metric_type=mt_b, order=1)

        response = authenticated_client.patch(
            "/api/metric-types/favorites/reorder/",
            {"metric_type_ids": [mt_b.id, mt_a.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        fav_a.refresh_from_db()
        fav_b.refresh_from_db()
        assert fav_b.order == 0
        assert fav_a.order == 1

    def test_reorder_rejects_mismatched_ids(
        self, authenticated_client, regular_user, number_metric_type
    ):
        baker.make(FavoriteMetric, user=regular_user, metric_type=number_metric_type)
        other_metric_type = baker.make("metrics.MetricType", value_type="number")

        response = authenticated_client.patch(
            "/api/metric-types/favorites/reorder/",
            {"metric_type_ids": [number_metric_type.id, other_metric_type.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reorder_rejects_empty_list(
        self, authenticated_client, regular_user, number_metric_type
    ):
        baker.make(FavoriteMetric, user=regular_user, metric_type=number_metric_type)
        response = authenticated_client.patch(
            "/api/metric-types/favorites/reorder/", {"metric_type_ids": []}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_anonymous_cannot_reorder(self, api_client):
        response = api_client.patch(
            "/api/metric-types/favorites/reorder/", {"metric_type_ids": [1]}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_reorder_using_another_users_favorite(
        self, authenticated_client, regular_user, other_user, number_metric_type
    ):
        baker.make(FavoriteMetric, user=other_user, metric_type=number_metric_type)
        response = authenticated_client.patch(
            "/api/metric-types/favorites/reorder/",
            {"metric_type_ids": [number_metric_type.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
