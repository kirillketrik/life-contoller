"""Write-side logic that doesn't fit in a serializer's create/update — see
CLAUDE.md's backend-layering convention. Creating or replacing a `FoodItem`'s
`FoodNutrientValue` rows is a multi-model write that should commit atomically
with the `FoodItem` itself, same shape as
`apps.metrics.services.create_metric_type_with_choices`. Recomputing a day's
materialized nutrition-total `MetricEntry` rows is a cross-app write (this
app writing into `apps.metrics`) triggered by `MealEntry` writes.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime as datetime_cls
from datetime import time

from django.db import transaction
from django.utils import timezone

from apps.metrics.models import MetricEntry, MetricType

from . import selectors
from .models import FoodItem, FoodNutrientValue, MealEntry, MealPlanEntry, Recipe, RecipeIngredient

# key -> MetricType.name of the materialized daily-total metric. Looked up by
# name (not a hardcoded id) so this app never depends on apps.metrics
# migration-assigned ids — same "match on name" convention seed_metrics/
# seed_nutrients already use. Shared with
# apps.nutrition.management.commands.seed_nutrition_metrics, which is what
# actually creates these MetricTypes.
DAILY_METRIC_NAMES: dict[str, str] = {
    "calories": "Калории (день)",
    "protein": "Белки (день)",
    "fat": "Жиры (день)",
    "carbs": "Углеводы (день)",
}


def create_food_item_with_nutrients(
    *, validated_data: dict, nutrient_values_data: list[dict], user
) -> FoodItem:
    with transaction.atomic():
        food_item = FoodItem.objects.create(owner=user, **validated_data)
        _replace_nutrient_values(food_item, nutrient_values_data)
    return food_item


def update_food_item_nutrients(*, food_item: FoodItem, nutrient_values_data: list[dict]) -> None:
    with transaction.atomic():
        _replace_nutrient_values(food_item, nutrient_values_data)


def _replace_nutrient_values(food_item: FoodItem, nutrient_values_data: list[dict]) -> None:
    food_item.nutrient_values.all().delete()
    FoodNutrientValue.objects.bulk_create(
        [
            FoodNutrientValue(
                food_item=food_item,
                nutrient_type=value["nutrient_type"],
                amount_per_100g=value["amount_per_100g"],
            )
            for value in nutrient_values_data
        ]
    )


def create_recipe_with_ingredients(
    *, validated_data: dict, ingredients_data: list[dict], user
) -> Recipe:
    with transaction.atomic():
        recipe = Recipe.objects.create(owner=user, **validated_data)
        _replace_ingredients(recipe, ingredients_data)
    return recipe


def update_recipe_ingredients(*, recipe: Recipe, ingredients_data: list[dict]) -> None:
    with transaction.atomic():
        _replace_ingredients(recipe, ingredients_data)


def _replace_ingredients(recipe: Recipe, ingredients_data: list[dict]) -> None:
    recipe.ingredients.all().delete()
    RecipeIngredient.objects.bulk_create(
        [
            RecipeIngredient(
                recipe=recipe,
                food_item=item["food_item"],
                quantity_g=item["quantity_g"],
            )
            for item in ingredients_data
        ]
    )


def recompute_daily_nutrition_metrics(*, user, entry_date: date_cls) -> None:
    """Recomputes `entry_date`'s calorie/macro totals from `user`'s
    `MealEntry` rows and materializes them as ordinary `MetricEntry` rows on
    the shared metrics layer — daily nutrition totals are exposed through the
    existing metrics infrastructure (charts, timeframes, dashboard elements)
    rather than a parallel stats system, per CLAUDE.md's "Integration with
    metrics" decision. Called from `MealEntryViewSet` after every
    create/update/delete, once per date touched.

    Deletes the materialized entry for a metric/date with nothing left to
    total, rather than persisting an explicit zero — "no data that day" and
    "logged zero" are different things, and there's no meal-logging path that
    produces a legitimate all-zero day. Silently skips a daily-total metric
    type that hasn't been seeded yet (see `seed_nutrition_metrics`) — same
    tolerance the formula engine already has for a formula referencing a
    metric type nobody has logged data for yet.

    Sums via `selectors.meal_entry_macro_totals`, the same function
    `MealEntrySerializer` uses — a day's total is correct whether its entries
    log a `FoodItem` directly, a `Recipe`, or a mix of both, with no
    special-casing here.
    """
    entries = list(selectors.meal_entry_list_for_user(user=user, entry_date=str(entry_date)))
    totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for entry in entries:
        entry_totals = selectors.meal_entry_macro_totals(entry)
        for key in totals:
            totals[key] += entry_totals[key]

    recorded_at = timezone.make_aware(
        datetime_cls.combine(entry_date, time(12, 0)), timezone.get_current_timezone()
    )

    for key, metric_name in DAILY_METRIC_NAMES.items():
        metric_type = MetricType.objects.filter(name=metric_name).first()
        if metric_type is None:
            continue
        existing = MetricEntry.objects.filter(
            metric_type=metric_type, owner=user, recorded_at__date=entry_date
        ).first()
        if not entries:
            if existing is not None:
                existing.delete()
            continue
        value = round(totals[key], 2)
        if existing is not None:
            existing.value = value
            existing.save(update_fields=["value", "updated_at"])
        else:
            MetricEntry.objects.create(
                metric_type=metric_type, owner=user, value=value, recorded_at=recorded_at
            )


def mark_meal_plan_entry_eaten(*, plan_entry: MealPlanEntry) -> MealEntry:
    """Converts a planned meal into a real, logged `MealEntry` — the one
    action that makes a plan actually count. A `MealPlanEntry` by itself
    never feeds the daily-total materialization; only the `MealEntry` this
    creates does, through the exact same `MealEntryViewSet.perform_create`-
    style call to `recompute_daily_nutrition_metrics` a normal logged meal
    triggers.

    Defaults the new entry's time to noon of the plan's date — same
    "noon local time" stand-in `recompute_daily_nutrition_metrics` already
    uses for materialized entries, since a plan only ever carries a date, not
    a time of day. Raises `ValueError` if the plan was already marked eaten
    (idempotency guard, same "reject a second write" shape as
    `MetricType.is_singleton` enforcement) — the caller maps this to a 400.
    """
    if plan_entry.resulting_meal_entry_id is not None:
        raise ValueError("This planned meal has already been marked as eaten.")

    at = timezone.make_aware(
        datetime_cls.combine(plan_entry.date, time(12, 0)), timezone.get_current_timezone()
    )
    with transaction.atomic():
        meal_entry = MealEntry.objects.create(
            owner=plan_entry.owner,
            datetime=at,
            meal_type=plan_entry.meal_type,
            food_item=plan_entry.food_item,
            recipe=plan_entry.recipe,
            quantity_g=plan_entry.quantity_g,
            servings=plan_entry.servings,
        )
        plan_entry.resulting_meal_entry = meal_entry
        plan_entry.save(update_fields=["resulting_meal_entry", "updated_at"])
    recompute_daily_nutrition_metrics(user=plan_entry.owner, entry_date=meal_entry.datetime.date())
    return meal_entry
