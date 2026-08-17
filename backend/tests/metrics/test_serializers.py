import pytest
from django.utils import timezone
from model_bakery import baker

from apps.metrics.models import ValueType
from apps.metrics.serializers import MetricEntrySerializer

pytestmark = pytest.mark.django_db


def _request(rf, user):
    request = rf.post("/")
    request.user = user
    return request


def _serialize(rf, user, metric_type, value):
    data = {
        "metric_type": metric_type.id,
        "value": value,
        "recorded_at": timezone.now(),
    }
    return MetricEntrySerializer(data=data, context={"request": _request(rf, user)})


def test_number_metric_rejects_text_value(rf, regular_user, faker):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.NUMBER)
    serializer = _serialize(rf, regular_user, metric_type, faker.word())
    assert not serializer.is_valid()
    assert "value" in serializer.errors


def test_number_metric_rejects_boolean_value(rf, regular_user):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.NUMBER)
    serializer = _serialize(rf, regular_user, metric_type, True)
    assert not serializer.is_valid()
    assert "value" in serializer.errors


def test_number_metric_accepts_number_value(rf, regular_user, faker):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.NUMBER)
    serializer = _serialize(
        rf, regular_user, metric_type, faker.pyfloat(min_value=0, max_value=200)
    )
    assert serializer.is_valid(), serializer.errors


def test_boolean_metric_accepts_boolean_value(rf, regular_user, faker):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.BOOLEAN)
    serializer = _serialize(rf, regular_user, metric_type, faker.boolean())
    assert serializer.is_valid(), serializer.errors


def test_text_metric_accepts_text_value(rf, regular_user, faker):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.TEXT)
    serializer = _serialize(rf, regular_user, metric_type, faker.sentence())
    assert serializer.is_valid(), serializer.errors


def test_create_sets_owner_from_request(rf, regular_user):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.NUMBER)
    serializer = _serialize(rf, regular_user, metric_type, 70)
    assert serializer.is_valid(), serializer.errors
    entry = serializer.save()
    assert entry.owner == regular_user
