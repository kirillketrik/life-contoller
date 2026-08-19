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

from .models import FoodItem, FoodNutrientValue, MealEntry

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
    """
    entries = list(
        MealEntry.objects.filter(owner=user, datetime__date=entry_date).select_related("food_item")
    )
    totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for entry in entries:
        factor = float(entry.quantity_g) / 100
        totals["calories"] += float(entry.food_item.calories_per_100g) * factor
        totals["protein"] += float(entry.food_item.protein_per_100g) * factor
        totals["fat"] += float(entry.food_item.fat_per_100g) * factor
        totals["carbs"] += float(entry.food_item.carbs_per_100g) * factor

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
