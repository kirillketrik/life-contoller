from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from apps.metrics.formula_engine import builtins
from apps.metrics.models import (
    DashboardElement,
    FormulaDefinition,
    MetricEntry,
    MetricType,
    ValueType,
)

pytestmark = pytest.mark.django_db


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _element_url(metric_type) -> str:
    return f"/api/metric-types/{metric_type.id}/dashboard-element/"


class TestDashboardElementConfig:
    def test_anonymous_cannot_configure(self, api_client, number_metric_type):
        response = api_client.patch(
            _element_url(number_metric_type), {"show_chart": True}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_create_config(
        self, authenticated_client, number_metric_type, regular_user
    ):
        response = authenticated_client.patch(
            _element_url(number_metric_type),
            {"show_chart": True, "show_current": True, "timeframe": "30d"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        element = DashboardElement.objects.get(user=regular_user, metric_type=number_metric_type)
        assert element.show_chart is True
        assert element.show_current is True
        assert element.timeframe == "30d"
        assert response.data["metric_type"]["id"] == number_metric_type.id

    def test_patch_updates_existing_config_instead_of_duplicating(
        self, authenticated_client, number_metric_type, regular_user
    ):
        authenticated_client.patch(
            _element_url(number_metric_type), {"show_chart": True}, format="json"
        )
        authenticated_client.patch(
            _element_url(number_metric_type), {"show_max": True}, format="json"
        )
        assert DashboardElement.objects.filter(
            user=regular_user, metric_type=number_metric_type
        ).count() == 1
        element = DashboardElement.objects.get(user=regular_user, metric_type=number_metric_type)
        assert element.show_max is True
        # the second PATCH omitted show_chart, so BooleanField(default=False) resets it —
        # PATCH here behaves as a full replace of the element's flags, not a partial merge
        assert element.show_chart is False

    def test_requires_at_least_one_element_enabled(self, authenticated_client, number_metric_type):
        response = authenticated_client.patch(_element_url(number_metric_type), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_custom_timeframe_requires_both_dates(self, authenticated_client, number_metric_type):
        response = authenticated_client.patch(
            _element_url(number_metric_type),
            {"show_chart": True, "timeframe": "custom", "custom_range_start": "2026-01-01"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_custom_timeframe_start_after_end_rejected(
        self, authenticated_client, number_metric_type
    ):
        response = authenticated_client.patch(
            _element_url(number_metric_type),
            {
                "show_chart": True,
                "timeframe": "custom",
                "custom_range_start": "2026-02-01",
                "custom_range_end": "2026-01-01",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_removes_config(self, authenticated_client, number_metric_type, regular_user):
        baker.make(
            DashboardElement, user=regular_user, metric_type=number_metric_type, show_chart=True
        )
        response = authenticated_client.delete(_element_url(number_metric_type))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not DashboardElement.objects.filter(
            user=regular_user, metric_type=number_metric_type
        ).exists()

    def test_delete_when_not_configured_is_a_noop(self, authenticated_client, number_metric_type):
        response = authenticated_client.delete(_element_url(number_metric_type))
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_configuring_unknown_metric_type_404s(self, authenticated_client):
        response = authenticated_client.patch(
            "/api/metric-types/999999/dashboard-element/", {"show_chart": True}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDashboardElementList:
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/dashboard-elements/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_scoped_per_user(
        self, authenticated_client, number_metric_type, regular_user, other_user
    ):
        baker.make(
            DashboardElement, user=other_user, metric_type=number_metric_type, show_chart=True
        )
        mine = baker.make(
            DashboardElement, user=regular_user, metric_type=number_metric_type, show_chart=True
        )

        response = authenticated_client.get("/api/dashboard-elements/")
        assert response.status_code == status.HTTP_200_OK
        returned_ids = {item["id"] for item in response.data}
        assert returned_ids == {mine.id}

    def test_current_is_latest_even_outside_the_selected_timeframe(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            DashboardElement,
            user=regular_user,
            metric_type=number_metric_type,
            show_current=True,
            timeframe="7d",
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=88,
            recorded_at=timezone.now() - timedelta(days=30),
        )

        response = authenticated_client.get("/api/dashboard-elements/")
        [element] = response.data
        assert element["current"] == 88

    def test_max_min_avg_scoped_to_resolved_range(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            DashboardElement,
            user=regular_user,
            metric_type=number_metric_type,
            show_max=True,
            show_min=True,
            show_avg=True,
            timeframe="30d",
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=999,
            recorded_at=timezone.now() - timedelta(days=60),
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=70,
            recorded_at=timezone.now() - timedelta(days=1),
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=80,
            recorded_at=timezone.now(),
        )

        response = authenticated_client.get("/api/dashboard-elements/")
        [element] = response.data
        assert element["max"] == 80
        assert element["min"] == 70
        assert element["avg"] == 75

    def test_chart_buckets_only_present_when_show_chart_true(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            DashboardElement,
            user=regular_user,
            metric_type=number_metric_type,
            show_max=True,
            timeframe="30d",
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=70,
            recorded_at=timezone.now(),
        )

        response = authenticated_client.get("/api/dashboard-elements/")
        [element] = response.data
        assert element["buckets"] == []
        assert element["max"] == 70

    def test_custom_range_resolves_correctly(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            DashboardElement,
            user=regular_user,
            metric_type=number_metric_type,
            show_max=True,
            timeframe="custom",
            custom_range_start=dt(2026, 1, 1).date(),
            custom_range_end=dt(2026, 1, 31).date(),
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=50,
            recorded_at=dt(2026, 1, 15, 12),
        )
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=999,
            recorded_at=dt(2026, 2, 15, 12),
        )

        response = authenticated_client.get("/api/dashboard-elements/")
        [element] = response.data
        assert element["max"] == 50

    def test_computed_metric_type_works_the_same_as_regular(
        self, authenticated_client, regular_user, db
    ):
        weight = baker.make(MetricType, value_type=ValueType.NUMBER, unit="kg")
        height = baker.make(MetricType, value_type=ValueType.NUMBER, unit="cm")
        bmi = baker.make(MetricType, value_type=ValueType.NUMBER, is_computed=True)
        baker.make(
            FormulaDefinition,
            computed_metric_type=bmi,
            expression=builtins.build_bmi(weight_kg_id=weight.id, height_cm_id=height.id),
        )
        baker.make(
            MetricEntry,
            metric_type=weight,
            owner=regular_user,
            value=70,
            recorded_at=timezone.now(),
        )
        baker.make(
            MetricEntry,
            metric_type=height,
            owner=regular_user,
            value=175,
            recorded_at=timezone.now(),
        )
        baker.make(
            DashboardElement,
            user=regular_user,
            metric_type=bmi,
            show_current=True,
            show_chart=True,
            show_max=True,
            timeframe="30d",
        )

        response = authenticated_client.get("/api/dashboard-elements/")
        [element] = response.data
        expected = 70 / (1.75**2)
        assert element["current"] == pytest.approx(expected)
        assert element["max"] == pytest.approx(expected)
        assert len(element["buckets"]) == 1

    def test_element_with_no_data_degrades_gracefully(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            DashboardElement,
            user=regular_user,
            metric_type=number_metric_type,
            show_current=True,
            show_chart=True,
            show_max=True,
            show_min=True,
            show_avg=True,
            timeframe="30d",
        )
        response = authenticated_client.get("/api/dashboard-elements/")
        assert response.status_code == status.HTTP_200_OK
        [element] = response.data
        assert element["current"] is None
        assert element["max"] is None
        assert element["min"] is None
        assert element["avg"] is None
        assert element["buckets"] == []

    def test_includes_period_changes(self, authenticated_client, number_metric_type, regular_user):
        baker.make(
            DashboardElement, user=regular_user, metric_type=number_metric_type, show_current=True
        )
        response = authenticated_client.get("/api/dashboard-elements/")
        [element] = response.data
        assert element["period_changes"].keys() == {"24h", "7d", "30d", "3m", "1y"}

    def test_element_metric_type_matches_full_metric_type_shape(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            DashboardElement, user=regular_user, metric_type=number_metric_type, show_current=True
        )
        response = authenticated_client.get("/api/dashboard-elements/")
        [element] = response.data
        assert element["metric_type"].keys() == {
            "id",
            "name",
            "unit",
            "value_type",
            "aggregation",
            "is_computed",
            "is_singleton",
            "created_by",
            "created_at",
            "updated_at",
            "choices",
        }


class TestDashboardElementReorder:
    def test_reorder_persists_order(self, authenticated_client, regular_user):
        mt_a = baker.make(MetricType, value_type="number")
        mt_b = baker.make(MetricType, value_type="number")
        el_a = baker.make(
            DashboardElement, user=regular_user, metric_type=mt_a, show_chart=True, order=0
        )
        el_b = baker.make(
            DashboardElement, user=regular_user, metric_type=mt_b, show_chart=True, order=1
        )

        response = authenticated_client.patch(
            "/api/dashboard-elements/reorder/",
            {"metric_type_ids": [mt_b.id, mt_a.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        el_a.refresh_from_db()
        el_b.refresh_from_db()
        assert el_b.order == 0
        assert el_a.order == 1

    def test_reorder_rejects_mismatched_ids(
        self, authenticated_client, regular_user, number_metric_type
    ):
        baker.make(
            DashboardElement, user=regular_user, metric_type=number_metric_type, show_chart=True
        )
        other_metric_type = baker.make(MetricType, value_type="number")

        response = authenticated_client.patch(
            "/api/dashboard-elements/reorder/",
            {"metric_type_ids": [number_metric_type.id, other_metric_type.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reorder_rejects_empty_list(
        self, authenticated_client, regular_user, number_metric_type
    ):
        baker.make(
            DashboardElement, user=regular_user, metric_type=number_metric_type, show_chart=True
        )
        response = authenticated_client.patch(
            "/api/dashboard-elements/reorder/", {"metric_type_ids": []}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_anonymous_cannot_reorder(self, api_client):
        response = api_client.patch(
            "/api/dashboard-elements/reorder/", {"metric_type_ids": [1]}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_reorder_using_another_users_element(
        self, authenticated_client, regular_user, other_user, number_metric_type
    ):
        baker.make(
            DashboardElement, user=other_user, metric_type=number_metric_type, show_chart=True
        )
        response = authenticated_client.patch(
            "/api/dashboard-elements/reorder/",
            {"metric_type_ids": [number_metric_type.id]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
