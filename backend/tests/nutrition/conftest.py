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
def second_food_item(regular_user):
    return baker.make(
        "nutrition.FoodItem",
        owner=regular_user,
        name="Рис",
        calories_per_100g=130,
        protein_per_100g=2.7,
        fat_per_100g=0.3,
        carbs_per_100g=28,
    )


@pytest.fixture
def recipe(regular_user, food_item, second_food_item):
    """A 2-serving recipe: 200g chicken breast + 100g rice."""
    recipe = baker.make("nutrition.Recipe", owner=regular_user, name="Курица с рисом", servings=2)
    baker.make(
        "nutrition.RecipeIngredient", recipe=recipe, food_item=food_item, quantity_g=200
    )
    baker.make(
        "nutrition.RecipeIngredient", recipe=recipe, food_item=second_food_item, quantity_g=100
    )
    return recipe


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
