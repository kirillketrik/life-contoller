import pytest
from model_bakery import baker

from apps.metrics.models import ValueType


@pytest.fixture
def other_user(db):
    """A second plain user, distinct from `regular_user`, for ownership/scoping tests."""
    return baker.make("users.User")


@pytest.fixture
def number_metric_type(db):
    return baker.make("metrics.MetricType", value_type=ValueType.NUMBER, unit="kg")


@pytest.fixture
def metric_entry(number_metric_type, regular_user):
    return baker.make(
        "metrics.MetricEntry",
        metric_type=number_metric_type,
        owner=regular_user,
        value=70,
    )
