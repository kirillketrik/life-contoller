import pytest
from model_bakery import baker
from rest_framework import status

from apps.nutrition.models import FoodItem

pytestmark = pytest.mark.django_db


class TestFoodItemPermissions:
    def test_anonymous_cannot_list(self, api_client):
        response = api_client.get("/api/food-items/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_create_own_food_item(self, authenticated_client):
        response = authenticated_client.post(
            "/api/food-items/",
            {
                "name": "Овсянка",
                "brand": "",
                "calories_per_100g": "389.00",
                "protein_per_100g": "16.90",
                "fat_per_100g": "6.90",
                "carbs_per_100g": "66.30",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["source"] == "own"
        assert response.data["is_verified"] is True

    def test_user_only_sees_own_food_items(self, authenticated_client, regular_user, other_user):
        baker.make(FoodItem, owner=other_user, name="Чужой продукт")
        mine = baker.make(FoodItem, owner=regular_user, name="Мой продукт")
        response = authenticated_client.get("/api/food-items/")
        returned_ids = {item["id"] for item in response.data["results"]}
        assert returned_ids == {mine.id}

    def test_user_cannot_edit_another_users_food_item(self, authenticated_client, other_user):
        theirs = baker.make(FoodItem, owner=other_user, name="Чужой продукт")
        response = authenticated_client.patch(
            f"/api/food-items/{theirs.id}/", {"name": "Переименовано"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_search_filters_by_name(self, authenticated_client, regular_user):
        baker.make(FoodItem, owner=regular_user, name="Куриная грудка")
        baker.make(FoodItem, owner=regular_user, name="Рис")
        response = authenticated_client.get("/api/food-items/?search=курин")
        names = {item["name"] for item in response.data["results"]}
        assert names == {"Куриная грудка"}


class TestFoodItemNutrientValues:
    def test_create_with_nutrient_values(self, authenticated_client, nutrient_type):
        response = authenticated_client.post(
            "/api/food-items/",
            {
                "name": "Апельсин",
                "calories_per_100g": "47.00",
                "protein_per_100g": "0.90",
                "fat_per_100g": "0.10",
                "carbs_per_100g": "11.80",
                "nutrient_values": [
                    {"nutrient_type": nutrient_type.id, "amount_per_100g": "53.200"}
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data["nutrient_values"]) == 1
        assert response.data["nutrient_values"][0]["nutrient_type_name"] == nutrient_type.name

    def test_update_replaces_nutrient_values(self, authenticated_client, food_item, nutrient_type):
        response = authenticated_client.patch(
            f"/api/food-items/{food_item.id}/",
            {"nutrient_values": [{"nutrient_type": nutrient_type.id, "amount_per_100g": "10.000"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["nutrient_values"]) == 1

        response = authenticated_client.patch(
            f"/api/food-items/{food_item.id}/", {"nutrient_values": []}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["nutrient_values"] == []

    def test_duplicate_nutrient_type_rejected(self, authenticated_client, nutrient_type):
        response = authenticated_client.post(
            "/api/food-items/",
            {
                "name": "Апельсин",
                "calories_per_100g": "47.00",
                "protein_per_100g": "0.90",
                "fat_per_100g": "0.10",
                "carbs_per_100g": "11.80",
                "nutrient_values": [
                    {"nutrient_type": nutrient_type.id, "amount_per_100g": "53.200"},
                    {"nutrient_type": nutrient_type.id, "amount_per_100g": "10.000"},
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
