import pytest
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import FormulaDefinition, MetricType, ValueType

pytestmark = pytest.mark.django_db


@pytest.fixture
def computed_type(db):
    return baker.make(MetricType, value_type=ValueType.NUMBER, is_computed=True)


@pytest.fixture
def weight_and_height(db):
    weight = baker.make(MetricType, value_type=ValueType.NUMBER, unit="kg")
    height = baker.make(MetricType, value_type=ValueType.NUMBER, unit="cm")
    return weight, height


class TestFormulaDefinitionPermissions:
    def test_anonymous_cannot_view(self, api_client):
        response = api_client.get("/api/formula-definitions/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_view(self, authenticated_client):
        response = authenticated_client.get("/api/formula-definitions/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_create(self, authenticated_client, computed_type, weight_and_height):
        weight, height = weight_and_height
        response = authenticated_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "formula_key": "bmi",
                "input_mapping": {"weight_kg": weight.id, "height_cm": height.id},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_view_and_create(self, admin_client, computed_type, weight_and_height):
        weight, height = weight_and_height
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "formula_key": "bmi",
                "input_mapping": {"weight_kg": weight.id, "height_cm": height.id},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

        list_response = admin_client.get("/api/formula-definitions/")
        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["count"] == 1


class TestFormulaDefinitionValidation:
    def test_computed_metric_type_must_be_marked_computed(self, admin_client, weight_and_height, db):
        weight, height = weight_and_height
        not_computed = baker.make(MetricType, value_type=ValueType.NUMBER, is_computed=False)
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": not_computed.id,
                "formula_key": "bmi",
                "input_mapping": {"weight_kg": weight.id, "height_cm": height.id},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_unknown_input_mapping_variables(self, admin_client, computed_type, weight_and_height):
        weight, height = weight_and_height
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "formula_key": "bmi",
                "input_mapping": {"weight_kg": weight.id, "not_a_real_variable": height.id},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_one_computed_metric_type_can_have_only_one_formula(
        self, admin_client, computed_type, weight_and_height
    ):
        weight, height = weight_and_height
        baker.make(
            FormulaDefinition,
            computed_metric_type=computed_type,
            formula_key=FormulaDefinition.FormulaKey.BMI,
            input_mapping={"weight_kg": weight.id, "height_cm": height.id},
        )
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "formula_key": "bmi",
                "input_mapping": {"weight_kg": weight.id, "height_cm": height.id},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
