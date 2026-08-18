import pytest
from model_bakery import baker
from rest_framework import status

from apps.metrics.formula_engine import builtins
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


def bmi_expression(weight, height):
    return builtins.build_bmi(weight_kg_id=weight.id, height_cm_id=height.id)


class TestFormulaDefinitionPermissions:
    def test_anonymous_cannot_view(self, api_client):
        response = api_client.get("/api/formula-definitions/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_view(self, authenticated_client):
        response = authenticated_client.get("/api/formula-definitions/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_create(
        self, authenticated_client, computed_type, weight_and_height
    ):
        weight, height = weight_and_height
        response = authenticated_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "expression": bmi_expression(weight, height),
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
                "expression": bmi_expression(weight, height),
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

        list_response = admin_client.get("/api/formula-definitions/")
        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["count"] == 1


class TestFormulaDefinitionValidation:
    def test_computed_metric_type_must_be_marked_computed(
        self, admin_client, weight_and_height, db
    ):
        weight, height = weight_and_height
        not_computed = baker.make(MetricType, value_type=ValueType.NUMBER, is_computed=False)
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": not_computed.id,
                "expression": bmi_expression(weight, height),
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_expression_referencing_unknown_metric_type(self, admin_client, computed_type):
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "expression": {"type": "metric", "metric_type_id": 999999},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_literal_division_by_zero(self, admin_client, computed_type, weight_and_height):
        weight, _ = weight_and_height
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "expression": {
                    "type": "binary_op",
                    "op": "/",
                    "left": {"type": "metric", "metric_type_id": weight.id},
                    "right": {"type": "constant", "value": 0},
                },
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_self_referencing_expression(self, admin_client, computed_type):
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "expression": {"type": "metric", "metric_type_id": computed_type.id},
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
            expression=bmi_expression(weight, height),
        )
        response = admin_client.post(
            "/api/formula-definitions/",
            {
                "computed_metric_type": computed_type.id,
                "expression": bmi_expression(weight, height),
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestFormulaPreview:
    def test_admin_can_preview_a_valid_expression(self, admin_client, weight_and_height):
        weight, height = weight_and_height
        response = admin_client.post(
            "/api/formula-definitions/preview/",
            {"expression": bmi_expression(weight, height)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["errors"] == []
        # no entries logged for the admin yet -> value is None, not an error
        assert response.data["value"] is None

    def test_preview_reports_validation_errors_without_saving(self, admin_client, computed_type):
        response = admin_client.post(
            "/api/formula-definitions/preview/",
            {
                "expression": {"type": "metric", "metric_type_id": computed_type.id},
                "computed_metric_type": computed_type.id,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] is None
        assert [e["code"] for e in response.data["errors"]] == ["circular_reference"]
        assert not FormulaDefinition.objects.exists()

    def test_regular_user_cannot_preview(self, authenticated_client, weight_and_height):
        weight, height = weight_and_height
        response = authenticated_client.post(
            "/api/formula-definitions/preview/",
            {"expression": bmi_expression(weight, height)},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
