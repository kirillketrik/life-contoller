import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import MetricEntry, ValueType

pytestmark = pytest.mark.django_db


class TestMetricTypePermissions:
    def test_anonymous_cannot_list(self, api_client):
        response = api_client.get("/api/metric-types/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_list(self, authenticated_client, number_metric_type):
        response = authenticated_client.get("/api/metric-types/")
        assert response.status_code == status.HTTP_200_OK

    def test_regular_user_cannot_create(self, authenticated_client, faker):
        response = authenticated_client.post(
            "/api/metric-types/",
            {"name": faker.unique.word(), "value_type": ValueType.NUMBER, "unit": "mg/dL"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create(self, admin_client, admin_user, faker):
        response = admin_client.post(
            "/api/metric-types/",
            {"name": faker.unique.word(), "value_type": ValueType.NUMBER, "unit": "mg/dL"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created_by"] == admin_user.id

    def test_superuser_is_treated_as_admin_without_group(self, api_client, faker):
        superuser = baker.make("users.User", is_superuser=True)
        api_client.force_authenticate(superuser)
        response = api_client.post(
            "/api/metric-types/",
            {"name": faker.unique.word(), "value_type": ValueType.NUMBER},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_regular_user_cannot_delete(self, authenticated_client, number_metric_type):
        response = authenticated_client.delete(f"/api/metric-types/{number_metric_type.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_search_filters_by_name(self, authenticated_client):
        baker.make("metrics.MetricType", name="Вес", value_type=ValueType.NUMBER)
        baker.make("metrics.MetricType", name="Рост", value_type=ValueType.NUMBER)

        response = authenticated_client.get("/api/metric-types/?search=вес")
        names = [item["name"] for item in response.data["results"]]
        assert names == ["Вес"]

    def test_search_is_case_insensitive_substring_match(self, authenticated_client):
        baker.make("metrics.MetricType", name="Обхват талии", value_type=ValueType.NUMBER)
        baker.make("metrics.MetricType", name="Рост", value_type=ValueType.NUMBER)

        response = authenticated_client.get("/api/metric-types/?search=ТАЛИ")
        names = [item["name"] for item in response.data["results"]]
        assert names == ["Обхват талии"]

    def test_no_search_returns_everything(self, authenticated_client, number_metric_type):
        baker.make("metrics.MetricType", name="Другая метрика", value_type=ValueType.NUMBER)

        response = authenticated_client.get("/api/metric-types/")
        assert len(response.data["results"]) == 2


class TestMetricEntryPermissions:
    def test_regular_user_can_create_own_entry(self, authenticated_client, regular_user, number_metric_type):
        response = authenticated_client.post(
            "/api/metric-entries/",
            {
                "metric_type": number_metric_type.id,
                "value": 71,
                "recorded_at": timezone.now().isoformat(),
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["owner"] == regular_user.id

    def test_admin_can_create_entry(self, admin_client, admin_user, number_metric_type):
        response = admin_client.post(
            "/api/metric-entries/",
            {
                "metric_type": number_metric_type.id,
                "value": 71,
                "recorded_at": timezone.now().isoformat(),
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["owner"] == admin_user.id

    def test_anonymous_cannot_create_entry(self, api_client, number_metric_type):
        response = api_client.post(
            "/api/metric-entries/",
            {
                "metric_type": number_metric_type.id,
                "value": 71,
                "recorded_at": timezone.now().isoformat(),
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_edit_own_entry(self, authenticated_client, metric_entry):
        response = authenticated_client.patch(f"/api/metric-entries/{metric_entry.id}/", {"value": 99})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == 99

    def test_regular_user_can_delete_own_entry(self, authenticated_client, metric_entry):
        response = authenticated_client.delete(f"/api/metric-entries/{metric_entry.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_regular_user_cannot_edit_others_entry(self, authenticated_client, number_metric_type, other_user):
        theirs = baker.make(
            MetricEntry, metric_type=number_metric_type, owner=other_user, value=1, recorded_at=timezone.now()
        )
        response = authenticated_client.patch(f"/api/metric-entries/{theirs.id}/", {"value": 99})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_cannot_edit_others_entry(self, admin_client, metric_entry):
        """MetricEntry is ownership-only, no admin override — same rule as
        MetricThreshold. `metric_entry` is owned by `regular_user`, not the
        admin client, so this 404s like any other user's entry would."""
        response = admin_client.patch(f"/api/metric-entries/{metric_entry.id}/", {"value": 99})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_only_sees_own_entries(self, authenticated_client, metric_entry, other_user):
        baker.make(
            MetricEntry,
            metric_type=metric_entry.metric_type,
            owner=other_user,
            value=80,
            recorded_at=timezone.now(),
        )
        response = authenticated_client.get("/api/metric-entries/")
        assert response.status_code == status.HTTP_200_OK
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {metric_entry.id}

    def test_can_filter_by_metric_type(self, authenticated_client, metric_entry, regular_user):
        other_type = baker.make("metrics.MetricType", value_type=ValueType.NUMBER)
        baker.make(
            MetricEntry,
            metric_type=other_type,
            owner=regular_user,
            value=1,
            recorded_at=timezone.now(),
        )
        response = authenticated_client.get(
            f"/api/metric-entries/?metric_type={metric_entry.metric_type_id}"
        )
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {metric_entry.id}

    def test_admin_only_sees_own_entries(self, admin_client, admin_user, metric_entry, other_user):
        """MetricEntry listing is ownership-only, same as MetricThreshold —
        an admin's own list never widens to include other users' entries,
        even though `metric_entry` and `other_entry` both exist."""
        own_entry = baker.make(
            MetricEntry,
            metric_type=metric_entry.metric_type,
            owner=admin_user,
            value=75,
            recorded_at=timezone.now(),
        )
        baker.make(
            MetricEntry,
            metric_type=metric_entry.metric_type,
            owner=other_user,
            value=80,
            recorded_at=timezone.now(),
        )
        response = admin_client.get("/api/metric-entries/")
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {own_entry.id}
