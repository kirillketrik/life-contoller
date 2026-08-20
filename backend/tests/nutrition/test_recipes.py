import pytest
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import MetricEntry
from apps.nutrition.models import Recipe

pytestmark = pytest.mark.django_db


class TestRecipePermissions:
    def test_anonymous_cannot_list(self, api_client):
        response = api_client.get("/api/recipes/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_create_own_recipe(self, authenticated_client, food_item):
        response = authenticated_client.post(
            "/api/recipes/",
            {
                "name": "Куриная грудка соло",
                "servings": 1,
                "ingredients": [{"food_item": food_item.id, "quantity_g": "200.00"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Куриная грудка соло"
        assert len(response.data["ingredients"]) == 1

    def test_user_only_sees_own_recipes(self, authenticated_client, regular_user, other_user):
        mine = baker.make(Recipe, owner=regular_user, name="Моё")
        baker.make(Recipe, owner=other_user, name="Чужое")
        response = authenticated_client.get("/api/recipes/")
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {mine.id}

    def test_user_cannot_edit_another_users_recipe(self, authenticated_client, other_user):
        theirs = baker.make(Recipe, owner=other_user, name="Чужое")
        response = authenticated_client.patch(
            f"/api/recipes/{theirs.id}/", {"name": "Переименовано"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_search_filters_by_name(self, authenticated_client, regular_user):
        baker.make(Recipe, owner=regular_user, name="Курица с рисом")
        baker.make(Recipe, owner=regular_user, name="Салат")
        response = authenticated_client.get("/api/recipes/?search=куриц")
        names = {item["name"] for item in response.data["results"]}
        assert names == {"Курица с рисом"}

    def test_at_least_one_ingredient_required(self, authenticated_client):
        response = authenticated_client.post(
            "/api/recipes/",
            {"name": "Пустой рецепт", "servings": 1, "ingredients": []},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_use_another_users_food_item_as_ingredient(
        self, authenticated_client, other_user
    ):
        theirs = baker.make(
            "nutrition.FoodItem",
            owner=other_user,
            calories_per_100g=1,
            protein_per_100g=1,
            fat_per_100g=1,
            carbs_per_100g=1,
        )
        response = authenticated_client.post(
            "/api/recipes/",
            {
                "name": "Рецепт",
                "servings": 1,
                "ingredients": [{"food_item": theirs.id, "quantity_g": "100.00"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestRecipeNutrientTotals:
    def test_totals_sum_across_ingredients(self, authenticated_client, recipe):
        response = authenticated_client.get(f"/api/recipes/{recipe.id}/")
        # chicken: 165*2 + 31*2 + 3.6*2 + 0*2 = 330/62/7.2/0
        # rice:    130*1 + 2.7*1 + 0.3*1 + 28*1 = 130/2.7/0.3/28
        assert response.data["total_calories"] == 460.0
        assert response.data["total_protein"] == 64.7
        assert response.data["total_fat"] == 7.5
        assert response.data["total_carbs"] == 28.0

    def test_per_serving_divides_by_servings(self, authenticated_client, recipe):
        response = authenticated_client.get(f"/api/recipes/{recipe.id}/")
        # recipe has servings=2
        assert response.data["calories_per_serving"] == 230.0
        assert response.data["protein_per_serving"] == 32.35
        assert response.data["fat_per_serving"] == 3.75
        assert response.data["carbs_per_serving"] == 14.0

    def test_update_replaces_ingredients_and_recomputes_totals(
        self, authenticated_client, recipe, food_item
    ):
        response = authenticated_client.patch(
            f"/api/recipes/{recipe.id}/",
            {"ingredients": [{"food_item": food_item.id, "quantity_g": "100.00"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["ingredients"]) == 1
        # chicken 165 kcal/100g * 100g / 100 = 165
        assert response.data["total_calories"] == 165.0


class TestMealEntryWithRecipe:
    def import_payload(self, recipe, **overrides):
        payload = {
            "datetime": "2026-01-01T08:00:00Z",
            "meal_type": "breakfast",
            "recipe": recipe.id,
            "servings": "1.00",
        }
        payload.update(overrides)
        return payload

    def test_can_log_a_meal_against_own_recipe(self, authenticated_client, recipe):
        response = authenticated_client.post(
            "/api/meal-entries/", self.import_payload(recipe), format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["recipe_name"] == recipe.name
        assert response.data["food_item_name"] is None
        # per-serving calories (230) * 1 serving eaten = 230
        assert response.data["calories"] == 230.0

    def test_servings_scale_the_totals(self, authenticated_client, recipe):
        response = authenticated_client.post(
            "/api/meal-entries/",
            self.import_payload(recipe, servings="0.5"),
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["calories"] == 115.0  # 230 * 0.5

    def test_cannot_log_against_another_users_recipe(self, authenticated_client, other_user):
        theirs = baker.make(Recipe, owner=other_user, name="Чужой рецепт")
        response = authenticated_client.post(
            "/api/meal-entries/", self.import_payload(theirs), format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_both_food_item_and_recipe_rejected(self, authenticated_client, recipe, food_item):
        response = authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": "2026-01-01T08:00:00Z",
                "meal_type": "breakfast",
                "recipe": recipe.id,
                "food_item": food_item.id,
                "servings": "1.00",
                "quantity_g": "100.00",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_neither_food_item_nor_recipe_rejected(self, authenticated_client):
        response = authenticated_client.post(
            "/api/meal-entries/",
            {"datetime": "2026-01-01T08:00:00Z", "meal_type": "breakfast"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_servings_must_be_positive(self, authenticated_client, recipe):
        response = authenticated_client.post(
            "/api/meal-entries/",
            self.import_payload(recipe, servings="0.00"),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestDailyNutritionMaterializationWithRecipe:
    def test_recipe_based_entry_materializes_daily_totals(
        self, authenticated_client, recipe, daily_nutrition_metric_types, regular_user
    ):
        authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": "2026-01-01T08:00:00Z",
                "meal_type": "breakfast",
                "recipe": recipe.id,
                "servings": "1.00",
            },
            format="json",
        )
        calories_entry = MetricEntry.objects.get(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        )
        assert calories_entry.value == 230.0

    def test_food_item_and_recipe_entries_sum_together(
        self, authenticated_client, recipe, food_item, daily_nutrition_metric_types, regular_user
    ):
        authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": "2026-01-01T08:00:00Z",
                "meal_type": "breakfast",
                "recipe": recipe.id,
                "servings": "1.00",
            },
            format="json",
        )
        authenticated_client.post(
            "/api/meal-entries/",
            {
                "datetime": "2026-01-01T13:00:00Z",
                "meal_type": "lunch",
                "food_item": food_item.id,
                "quantity_g": "100.00",
            },
            format="json",
        )
        calories_entry = MetricEntry.objects.get(
            metric_type=daily_nutrition_metric_types["calories"], owner=regular_user
        )
        # recipe serving 230 + 100g chicken (165) = 395
        assert calories_entry.value == 395.0
