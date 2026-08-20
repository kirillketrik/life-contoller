from datetime import UTC, datetime

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import MetricEntry
from apps.nutrition.models import MealEntry

pytestmark = pytest.mark.django_db


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


class TestMealEntryPermissions:
    def test_anonymous_cannot_list(self, api_client):
        response = api_client.get("/api/meal-entries/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_create_own_meal_entry(self, authenticated_client, food_item):
        response = authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": dt(2026, 1, 1, 8).isoformat(),
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "150.00",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["food_item_name"] == food_item.name
        # 165 kcal/100g * 150g / 100 = 247.5
        assert response.data["calories"] == 247.5

    def test_cannot_log_meal_against_another_users_food_item(
        self, authenticated_client, other_user
    ):
        theirs = baker.make(
            "nutrition.FoodItem",
            owner=other_user,
            calories_per_100g=100,
            protein_per_100g=1,
            fat_per_100g=1,
            carbs_per_100g=1,
        )
        response = authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": dt(2026, 1, 1, 8).isoformat(),
                "meal_type": "breakfast",
                "food_item": theirs.id,
                "quantity_g": "100.00",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_user_only_sees_own_meal_entries(
        self, authenticated_client, regular_user, other_user, food_item
    ):
        mine = baker.make(
            MealEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            datetime=dt(2026, 1, 1, 8),
        )
        their_food = baker.make(
            "nutrition.FoodItem",
            owner=other_user,
            calories_per_100g=1,
            protein_per_100g=1,
            fat_per_100g=1,
            carbs_per_100g=1,
        )
        baker.make(
            MealEntry,
            owner=other_user,
            food_item=their_food,
            quantity_g=100,
            datetime=dt(2026, 1, 1, 8),
        )
        response = authenticated_client.get("/api/meal-entries/")
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {mine.id}

    def test_user_cannot_edit_another_users_meal_entry(self, authenticated_client, other_user):
        their_food = baker.make(
            "nutrition.FoodItem",
            owner=other_user,
            calories_per_100g=1,
            protein_per_100g=1,
            fat_per_100g=1,
            carbs_per_100g=1,
        )
        theirs = baker.make(
            MealEntry,
            owner=other_user,
            food_item=their_food,
            quantity_g=100,
            datetime=dt(2026, 1, 1, 8),
        )
        response = authenticated_client.patch(
            f"/api/meal-entries/{theirs.id}/", {"quantity_g": "50.00"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_quantity_must_be_positive(self, authenticated_client, food_item):
        response = authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": dt(2026, 1, 1, 8).isoformat(),
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "0.00",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_date_filter(self, authenticated_client, regular_user, food_item):
        baker.make(
            MealEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            datetime=dt(2026, 1, 1, 8),
        )
        baker.make(
            MealEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            datetime=dt(2026, 1, 2, 8),
        )
        response = authenticated_client.get("/api/meal-entries/?date=2026-01-01")
        assert len(response.data["results"]) == 1


class TestDailyNutritionMaterialization:
    def test_creating_a_meal_entry_materializes_daily_totals(
        self, authenticated_client, food_item, daily_nutrition_metric_types, regular_user
    ):
        authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": dt(2026, 1, 1, 8).isoformat(),
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "200.00",
            },
        )
        calories_entry = MetricEntry.objects.get(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        )
        # 165 kcal/100g * 200g / 100 = 330
        assert calories_entry.value == 330.0
        assert calories_entry.recorded_at.date().isoformat() == "2026-01-01"

        protein_entry = MetricEntry.objects.get(
            metric_type=daily_nutrition_metric_types["protein"], owner=regular_user
        )
        assert protein_entry.value == 62.0  # 31 * 200 / 100

    def test_two_meals_same_day_sum_together(
        self, authenticated_client, food_item, daily_nutrition_metric_types, regular_user
    ):
        for _ in range(2):
            authenticated_client.post(
                "/api/meal-entries/",
                {
                    "datetime": dt(2026, 1, 1, 8).isoformat(),
                    "meal_type": "breakfast",
                    "food_item": food_item.id,
                    "quantity_g": "100.00",
                },
            )
        calories_entry = MetricEntry.objects.get(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        )
        assert calories_entry.value == 330.0  # 165 * 2

    def test_deleting_the_last_entry_removes_the_materialized_metric(
        self, authenticated_client, food_item, daily_nutrition_metric_types, regular_user
    ):
        create_response = authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": dt(2026, 1, 1, 8).isoformat(),
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "100.00",
            },
        )
        assert MetricEntry.objects.filter(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        ).exists()

        authenticated_client.delete(f"/api/meal-entries/{create_response.data['id']}/")
        assert not MetricEntry.objects.filter(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        ).exists()

    def test_moving_an_entry_to_another_day_recomputes_both_days(
        self, authenticated_client, food_item, daily_nutrition_metric_types, regular_user
    ):
        create_response = authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": dt(2026, 1, 1, 8).isoformat(),
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "100.00",
            },
        )
        authenticated_client.patch(
            f"/api/meal-entries/{create_response.data['id']}/",
            {"datetime": dt(2026, 1, 2, 8).isoformat()},
        )

        calories_metric_type = daily_nutrition_metric_types["calories"]
        assert not MetricEntry.objects.filter(
            metric_type=calories_metric_type, owner=regular_user, recorded_at__date="2026-01-01"
        ).exists()
        assert MetricEntry.objects.filter(
            metric_type=calories_metric_type, owner=regular_user, recorded_at__date="2026-01-02"
        ).exists()

    def test_recompute_skips_unseeded_metric_types_without_error(
        self, authenticated_client, food_item
    ):
        # No daily_nutrition_metric_types fixture used here — the MetricTypes
        # don't exist, and this must not raise.
        response = authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": dt(2026, 1, 1, 8).isoformat(),
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "100.00",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_todays_materialized_entry_is_never_stamped_in_the_future(
        self, authenticated_client, food_item, daily_nutrition_metric_types, regular_user
    ):
        # A fixed noon-of-the-day timestamp would land in the future whenever
        # the entry is logged before noon UTC — invisible to
        # current_value_for_metric_type and any range query filtering on
        # recorded_at <= now, which looked exactly like the daily total
        # "not updating". Today's materialized entry must never be stamped
        # later than the actual current moment.
        today = timezone.now().date()
        authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": timezone.now().isoformat(),
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "100.00",
            },
        )
        calories_entry = MetricEntry.objects.get(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        )
        assert calories_entry.recorded_at.date() == today
        assert calories_entry.recorded_at <= timezone.now()
