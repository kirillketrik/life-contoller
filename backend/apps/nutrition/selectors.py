"""Read-only query logic for the nutrition app — see apps.metrics.selectors
for the convention this mirrors: views/viewsets never build querysets
inline, they call a selector here.
"""

from __future__ import annotations

from django.db.models import QuerySet

from .models import FoodItem, MealEntry, NutrientType


def nutrient_type_list() -> QuerySet[NutrientType]:
    """The nutrient catalog is shared, admin-defined, readable data —
    visible to any authenticated user, same as `metric_type_list`."""
    return NutrientType.objects.all()


def nutrient_type_get(*, nutrient_type_id: int) -> NutrientType | None:
    return NutrientType.objects.filter(id=nutrient_type_id).first()


def food_item_list_for_user(*, user, search: str | None = None) -> QuerySet[FoodItem]:
    """Food items owned by `user` only — not a shared catalog, every user
    keeps their own. `search` filters by name (uses the (owner, name) index)
    for the food-item picker used when logging meals."""
    queryset = FoodItem.objects.select_related("owner").prefetch_related(
        "nutrient_values__nutrient_type"
    ).filter(owner=user)
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset


def food_item_get_for_user(*, user, food_item_id: int) -> FoodItem | None:
    return food_item_list_for_user(user=user).filter(id=food_item_id).first()


def meal_entry_list_for_user(*, user, entry_date: str | None = None) -> QuerySet[MealEntry]:
    """Meal entries owned by `user` only — ownership, same as `FoodItem`.
    `entry_date` (an ISO `YYYY-MM-DD` string) narrows to one day's entries,
    for the food-diary day view."""
    queryset = MealEntry.objects.select_related("food_item").filter(owner=user)
    if entry_date:
        queryset = queryset.filter(datetime__date=entry_date)
    return queryset


def meal_entry_get_for_user(*, user, meal_entry_id: int) -> MealEntry | None:
    return meal_entry_list_for_user(user=user).filter(id=meal_entry_id).first()
