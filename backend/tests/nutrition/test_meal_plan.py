import pytest
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import MetricEntry
from apps.nutrition.models import MealEntry, MealPlanEntry

pytestmark = pytest.mark.django_db


class TestMealPlanEntryPermissions:
    def test_anonymous_cannot_list(self, api_client):
        response = api_client.get("/api/meal-plan-entries/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_plan_a_food_item(self, authenticated_client, food_item):
        response = authenticated_client.post(
            "/api/meal-plan-entries/",
            {
                "date": "2026-09-01",
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "quantity_g": "150.00",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["food_item_name"] == food_item.name
        assert response.data["is_eaten"] is False
        assert response.data["resulting_meal_entry"] is None
        # 165 kcal/100g * 150g / 100 = 247.5
        assert response.data["calories"] == 247.5

    def test_regular_user_can_plan_a_recipe(self, authenticated_client, recipe):
        response = authenticated_client.post(
            "/api/meal-plan-entries/",
            {"date": "2026-09-01", "meal_type": "lunch", "recipe": recipe.id, "servings": "1.5"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["recipe_name"] == recipe.name
        # 230 kcal/serving * 1.5 = 345
        assert response.data["calories"] == 345.0

    def test_cannot_plan_against_another_users_food_item(self, authenticated_client, other_user):
        theirs = baker.make(
            "nutrition.FoodItem",
            owner=other_user,
            calories_per_100g=100,
            protein_per_100g=1,
            fat_per_100g=1,
            carbs_per_100g=1,
        )
        response = authenticated_client.post(
            "/api/meal-plan-entries/",
            {
                "date": "2026-09-01",
                "meal_type": "breakfast",
                "food_item": theirs.id,
                "quantity_g": "100.00",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_must_provide_exactly_one_of_food_item_or_recipe(
        self, authenticated_client, food_item, recipe
    ):
        response = authenticated_client.post(
            "/api/meal-plan-entries/",
            {
                "date": "2026-09-01",
                "meal_type": "breakfast",
                "food_item": food_item.id,
                "recipe": recipe.id,
                "quantity_g": "100.00",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = authenticated_client.post(
            "/api/meal-plan-entries/", {"date": "2026-09-01", "meal_type": "breakfast"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_user_only_sees_own_planned_meals(
        self, authenticated_client, regular_user, other_user, food_item
    ):
        mine = baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-01",
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
            MealPlanEntry, owner=other_user, food_item=their_food, quantity_g=100, date="2026-09-01"
        )
        response = authenticated_client.get("/api/meal-plan-entries/")
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {mine.id}

    def test_user_cannot_edit_or_mark_eaten_anothers_plan(self, authenticated_client, other_user):
        their_food = baker.make(
            "nutrition.FoodItem",
            owner=other_user,
            calories_per_100g=1,
            protein_per_100g=1,
            fat_per_100g=1,
            carbs_per_100g=1,
        )
        theirs = baker.make(
            MealPlanEntry, owner=other_user, food_item=their_food, quantity_g=100, date="2026-09-01"
        )
        response = authenticated_client.patch(
            f"/api/meal-plan-entries/{theirs.id}/", {"quantity_g": "50.00"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        response = authenticated_client.post(f"/api/meal-plan-entries/{theirs.id}/mark-eaten/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_date_range_filter(self, authenticated_client, regular_user, food_item):
        baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-01",
        )
        baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-05",
        )
        baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-10",
        )
        response = authenticated_client.get(
            "/api/meal-plan-entries/?start_date=2026-09-02&end_date=2026-09-09"
        )
        assert len(response.data["results"]) == 1

        response = authenticated_client.get("/api/meal-plan-entries/?date=2026-09-01")
        assert len(response.data["results"]) == 1


class TestMarkEaten:
    def test_marking_eaten_creates_a_real_meal_entry(
        self, authenticated_client, regular_user, food_item
    ):
        plan = baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=150,
            date="2026-09-01",
        )
        response = authenticated_client.post(f"/api/meal-plan-entries/{plan.id}/mark-eaten/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_eaten"] is True
        assert response.data["resulting_meal_entry"] is not None

        entry = MealEntry.objects.get(id=response.data["resulting_meal_entry"])
        assert entry.owner_id == regular_user.id
        assert entry.food_item_id == food_item.id
        assert entry.quantity_g == 150
        assert entry.datetime.date().isoformat() == "2026-09-01"

    def test_marking_eaten_recomputes_daily_totals(
        self, authenticated_client, regular_user, food_item, daily_nutrition_metric_types
    ):
        plan = baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=200,
            date="2026-09-01",
        )
        authenticated_client.post(f"/api/meal-plan-entries/{plan.id}/mark-eaten/")

        calories_entry = MetricEntry.objects.get(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        )
        # 165 kcal/100g * 200g / 100 = 330
        assert calories_entry.value == 330.0

    def test_cannot_mark_already_eaten_plan_eaten_again(
        self, authenticated_client, regular_user, food_item
    ):
        plan = baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-01",
        )
        first = authenticated_client.post(f"/api/meal-plan-entries/{plan.id}/mark-eaten/")
        assert first.status_code == status.HTTP_200_OK

        second = authenticated_client.post(f"/api/meal-plan-entries/{plan.id}/mark-eaten/")
        assert second.status_code == status.HTTP_400_BAD_REQUEST

    def test_deleting_the_resulting_meal_entry_reverts_plan_to_not_eaten(
        self, authenticated_client, regular_user, food_item
    ):
        plan = baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-01",
        )
        mark_response = authenticated_client.post(f"/api/meal-plan-entries/{plan.id}/mark-eaten/")
        entry_id = mark_response.data["resulting_meal_entry"]

        authenticated_client.delete(f"/api/meal-entries/{entry_id}/")

        plan.refresh_from_db()
        assert plan.resulting_meal_entry_id is None

    def test_marking_a_recipe_plan_eaten_uses_per_serving_math(
        self, authenticated_client, regular_user, recipe
    ):
        plan = baker.make(
            MealPlanEntry, owner=regular_user, recipe=recipe, servings=1, date="2026-09-01"
        )
        response = authenticated_client.post(f"/api/meal-plan-entries/{plan.id}/mark-eaten/")
        entry = MealEntry.objects.get(id=response.data["resulting_meal_entry"])
        assert entry.recipe_id == recipe.id
        assert entry.servings == 1


class TestDuplicateDay:
    def test_duplicates_every_entry_from_source_to_target_date(
        self, authenticated_client, regular_user, food_item, recipe
    ):
        baker.make(
            MealPlanEntry,
            owner=regular_user,
            meal_type="breakfast",
            food_item=food_item,
            quantity_g=150,
            date="2026-09-01",
        )
        baker.make(
            MealPlanEntry,
            owner=regular_user,
            meal_type="lunch",
            recipe=recipe,
            servings=1,
            date="2026-09-01",
        )
        response = authenticated_client.post(
            "/api/meal-plan-entries/duplicate-day/",
            {"source_date": "2026-09-01", "target_date": "2026-09-08"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2

        target_entries = MealPlanEntry.objects.filter(owner=regular_user, date="2026-09-08")
        assert target_entries.count() == 2
        meal_types = {entry.meal_type for entry in target_entries}
        assert meal_types == {"breakfast", "lunch"}
        for entry in target_entries:
            assert entry.resulting_meal_entry_id is None
        # the source day's own entries must be untouched
        assert MealPlanEntry.objects.filter(owner=regular_user, date="2026-09-01").count() == 2

    def test_duplicating_an_empty_day_creates_nothing(self, authenticated_client):
        response = authenticated_client.post(
            "/api/meal-plan-entries/duplicate-day/",
            {"source_date": "2026-09-01", "target_date": "2026-09-08"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == []

    def test_duplicate_is_additive_onto_a_day_that_already_has_plans(
        self, authenticated_client, regular_user, food_item
    ):
        baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-01",
        )
        baker.make(
            MealPlanEntry,
            owner=regular_user,
            food_item=food_item,
            quantity_g=100,
            date="2026-09-08",
        )
        response = authenticated_client.post(
            "/api/meal-plan-entries/duplicate-day/",
            {"source_date": "2026-09-01", "target_date": "2026-09-08"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert MealPlanEntry.objects.filter(owner=regular_user, date="2026-09-08").count() == 2

    def test_only_duplicates_the_requesting_users_own_entries(
        self, authenticated_client, regular_user, other_user
    ):
        their_food = baker.make(
            "nutrition.FoodItem",
            owner=other_user,
            calories_per_100g=1,
            protein_per_100g=1,
            fat_per_100g=1,
            carbs_per_100g=1,
        )
        baker.make(
            MealPlanEntry, owner=other_user, food_item=their_food, quantity_g=100, date="2026-09-01"
        )
        response = authenticated_client.post(
            "/api/meal-plan-entries/duplicate-day/",
            {"source_date": "2026-09-01", "target_date": "2026-09-08"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == []
        assert not MealPlanEntry.objects.filter(owner=regular_user, date="2026-09-08").exists()

    def test_anonymous_cannot_duplicate(self, api_client):
        response = api_client.post(
            "/api/meal-plan-entries/duplicate-day/",
            {"source_date": "2026-09-01", "target_date": "2026-09-08"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_requires_both_dates(self, authenticated_client):
        response = authenticated_client.post(
            "/api/meal-plan-entries/duplicate-day/", {"source_date": "2026-09-01"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
