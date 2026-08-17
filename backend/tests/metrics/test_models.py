import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from model_bakery import baker

from apps.metrics.models import MetricEntry, MetricType, ValueType

pytestmark = pytest.mark.django_db


def test_str_returns_name():
    metric_type = baker.make(MetricType, name="Weight", value_type=ValueType.NUMBER)
    assert str(metric_type) == "Weight"


def test_name_is_unique():
    baker.make(MetricType, name="Weight", value_type=ValueType.NUMBER)
    with pytest.raises(IntegrityError), transaction.atomic():
        baker.make(MetricType, name="Weight", value_type=ValueType.NUMBER)


def test_entries_ordered_most_recent_first(number_metric_type, regular_user):
    older = baker.make(
        MetricEntry,
        metric_type=number_metric_type,
        owner=regular_user,
        value=250,
        recorded_at=timezone.now() - timezone.timedelta(days=1),
    )
    newer = baker.make(
        MetricEntry,
        metric_type=number_metric_type,
        owner=regular_user,
        value=500,
        recorded_at=timezone.now(),
    )
    assert list(MetricEntry.objects.all()) == [newer, older]


def test_context_is_optional(number_metric_type, regular_user):
    entry = baker.make(
        MetricEntry,
        metric_type=number_metric_type,
        owner=regular_user,
        context=None,
    )
    assert entry.context is None
