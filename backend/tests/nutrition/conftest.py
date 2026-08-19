import pytest
from model_bakery import baker

from apps.nutrition.models import NutrientCategory
from apps.nutrition.services import DAILY_METRIC_NAMES


@pytest.fixture
def nutrient_type(db):
    return baker.make(
        "nutrition.NutrientType", name="Витамин C", unit="mg", category=NutrientCategory.MICRO
    )


@pytest.fixture
def food_item(regular_user):
    return baker.make(
        "nutrition.FoodItem",
        owner=regular_user,
        name="Куриная грудка",
        calories_per_100g=165,
        protein_per_100g=31,
        fat_per_100g=3.6,
        carbs_per_100g=0,
    )


@pytest.fixture
def daily_nutrition_metric_types(db):
    """The four materialized daily-total MetricTypes, as `seed_nutrition_metrics`
    would create them — needed so `recompute_daily_nutrition_metrics` (which
    looks them up by name) has something to write into."""
    from apps.metrics.models import ValueType

    return {
        key: baker.make("metrics.MetricType", name=name, value_type=ValueType.NUMBER, unit="ккал")
        for key, name in DAILY_METRIC_NAMES.items()
    }
