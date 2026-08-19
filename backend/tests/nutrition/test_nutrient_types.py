import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestNutrientTypePermissions:
    def test_anonymous_cannot_list(self, api_client):
        response = api_client.get("/api/nutrient-types/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_can_read(self, authenticated_client, nutrient_type):
        response = authenticated_client.get("/api/nutrient-types/")
        assert response.status_code == status.HTTP_200_OK
        returned_ids = {item["id"] for item in response.data["results"]}
        assert nutrient_type.id in returned_ids

    def test_regular_user_cannot_create(self, authenticated_client):
        response = authenticated_client.post(
            "/api/nutrient-types/", {"name": "Йод", "unit": "mcg", "category": "micro"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create(self, admin_client):
        response = admin_client.post(
            "/api/nutrient-types/", {"name": "Йод", "unit": "mcg", "category": "micro"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["is_system"] is False

    def test_admin_can_delete(self, admin_client, nutrient_type):
        response = admin_client.delete(f"/api/nutrient-types/{nutrient_type.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
