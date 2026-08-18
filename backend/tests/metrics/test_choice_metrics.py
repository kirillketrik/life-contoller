import pytest
from model_bakery import baker

from apps.metrics.models import MetricType, MetricTypeChoice, ValueType

pytestmark = pytest.mark.django_db


def test_admin_creates_choice_metric_type_with_options(admin_client):
    response = admin_client.post(
        "/api/metric-types/",
        {
            "name": "Пол",
            "unit": "",
            "value_type": "choice",
            "aggregation": "",
            "choices": [
                {"code": "male", "label": "Мужской", "order": 0},
                {"code": "female", "label": "Женский", "order": 1},
            ],
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    metric_type = MetricType.objects.get(id=response.data["id"])
    assert list(metric_type.choices.values_list("code", "label")) == [
        ("male", "Мужской"),
        ("female", "Женский"),
    ]


def test_choice_metric_type_requires_at_least_one_option(admin_client):
    response = admin_client.post(
        "/api/metric-types/",
        {
            "name": "Пустой список",
            "unit": "",
            "value_type": "choice",
            "aggregation": "",
            "choices": [],
        },
        format="json",
    )
    assert response.status_code == 400
    assert "choices" in response.data


def test_choice_metric_type_rejects_duplicate_codes(admin_client):
    response = admin_client.post(
        "/api/metric-types/",
        {
            "name": "Дубликаты",
            "unit": "",
            "value_type": "choice",
            "aggregation": "",
            "choices": [
                {"code": "a", "label": "A", "order": 0},
                {"code": "a", "label": "B", "order": 1},
            ],
        },
        format="json",
    )
    assert response.status_code == 400
    assert "choices" in response.data


def test_numeric_value_is_optional_per_option(admin_client):
    response = admin_client.post(
        "/api/metric-types/",
        {
            "name": "Уровень активности",
            "unit": "",
            "value_type": "choice",
            "aggregation": "",
            "choices": [
                {
                    "code": "sedentary",
                    "label": "Сидячий образ жизни",
                    "numeric_value": 1.2,
                    "order": 0,
                },
                {"code": "light", "label": "Лёгкая активность", "numeric_value": 1.375, "order": 1},
            ],
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    choice = MetricTypeChoice.objects.get(code="sedentary")
    assert choice.numeric_value == 1.2


@pytest.fixture
def sex_metric_type(db):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.CHOICE, name="Пол")
    baker.make("metrics.MetricTypeChoice", metric_type=metric_type, code="male", label="Мужской")
    baker.make("metrics.MetricTypeChoice", metric_type=metric_type, code="female", label="Женский")
    return metric_type


def test_metric_entry_accepts_valid_choice_code(authenticated_client, sex_metric_type):
    response = authenticated_client.post(
        "/api/metric-entries/",
        {
            "metric_type": sex_metric_type.id,
            "value": "male",
            "recorded_at": "2026-01-01T00:00:00Z",
        },
        format="json",
    )
    assert response.status_code == 201, response.data


def test_metric_entry_rejects_unknown_choice_code(authenticated_client, sex_metric_type):
    response = authenticated_client.post(
        "/api/metric-entries/",
        {
            "metric_type": sex_metric_type.id,
            "value": "other",
            "recorded_at": "2026-01-01T00:00:00Z",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "value" in response.data


def test_updating_metric_type_replaces_choices(admin_client, sex_metric_type):
    response = admin_client.patch(
        f"/api/metric-types/{sex_metric_type.id}/",
        {"choices": [{"code": "unspecified", "label": "Не указано", "order": 0}]},
        format="json",
    )
    assert response.status_code == 200, response.data
    codes = list(
        MetricTypeChoice.objects.filter(metric_type=sex_metric_type).values_list("code", flat=True)
    )
    assert codes == ["unspecified"]


def test_deleting_metric_type_cascades_to_choices(admin_client, sex_metric_type):
    metric_type_id = sex_metric_type.id
    response = admin_client.delete(f"/api/metric-types/{metric_type_id}/")
    assert response.status_code == 204
    assert not MetricTypeChoice.objects.filter(metric_type_id=metric_type_id).exists()
