"""Read-only query logic for the nutrition app — see apps.metrics.selectors
for the convention this mirrors: views/viewsets never build querysets
inline, they call a selector here.
"""

from __future__ import annotations

from django.db.models import QuerySet

from .models import FoodItem, MealEntry, NutrientType, Recipe


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
    for the food-diary day view. `recipe__ingredients__food_item` is
    prefetched so `meal_entry_macro_totals` never re-queries per row when
    called from the serializer or from `services.recompute_daily_nutrition_metrics`."""
    queryset = MealEntry.objects.select_related("food_item", "recipe").prefetch_related(
        "recipe__ingredients__food_item"
    ).filter(owner=user)
    if entry_date:
        queryset = queryset.filter(datetime__date=entry_date)
    return queryset


def meal_entry_get_for_user(*, user, meal_entry_id: int) -> MealEntry | None:
    return meal_entry_list_for_user(user=user).filter(id=meal_entry_id).first()


def recipe_list_for_user(*, user, search: str | None = None) -> QuerySet[Recipe]:
    """Recipes owned by `user` only — ownership, same as `FoodItem`.
    `ingredients__food_item` is prefetched so `recipe_macro_totals` (called
    once per computed-total field on `RecipeSerializer`) never re-queries."""
    queryset = Recipe.objects.select_related("owner").prefetch_related(
        "ingredients__food_item"
    ).filter(owner=user)
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset


def recipe_get_for_user(*, user, recipe_id: int) -> Recipe | None:
    return recipe_list_for_user(user=user).filter(id=recipe_id).first()


def food_item_macro_totals(food_item: FoodItem, quantity_g) -> dict[str, float]:
    """`quantity_g` worth of `food_item`'s per-100g macros — the single place
    this "per-100g × quantity/100" arithmetic lives, shared by
    `MealEntrySerializer` (a food-item-based entry) and `recipe_macro_totals`
    (each ingredient line of a recipe)."""
    factor = float(quantity_g) / 100
    return {
        "calories": round(float(food_item.calories_per_100g) * factor, 2),
        "protein": round(float(food_item.protein_per_100g) * factor, 2),
        "fat": round(float(food_item.fat_per_100g) * factor, 2),
        "carbs": round(float(food_item.carbs_per_100g) * factor, 2),
    }


def recipe_macro_totals(recipe: Recipe) -> dict[str, float]:
    """Sums every ingredient's macros — whole-recipe totals, not per
    serving (see `recipe_macro_totals_per_serving` for that). Iterates
    `recipe.ingredients.all()` (never `.select_related()`/`.filter()`
    chained fresh) so a caller that prefetched `ingredients__food_item`
    (both `recipe_list_for_user` and `meal_entry_list_for_user` do) pays no
    extra query — Django's prefetch cache is only reused by a bare `.all()`."""
    totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for ingredient in recipe.ingredients.all():
        ingredient_totals = food_item_macro_totals(ingredient.food_item, ingredient.quantity_g)
        for key, value in ingredient_totals.items():
            totals[key] += value
    return {key: round(value, 2) for key, value in totals.items()}


def recipe_macro_totals_per_serving(recipe: Recipe) -> dict[str, float]:
    servings = recipe.servings or 1
    return {key: round(value / servings, 2) for key, value in recipe_macro_totals(recipe).items()}


def meal_entry_macro_totals(meal_entry: MealEntry) -> dict[str, float]:
    """Works uniformly for a food-item-based or recipe-based entry — the one
    place both are translated into calories/protein/fat/carbs, reused by
    `MealEntrySerializer` and `services.recompute_daily_nutrition_metrics`
    so the two can never compute a meal's totals differently."""
    if meal_entry.food_item_id is not None:
        return food_item_macro_totals(meal_entry.food_item, meal_entry.quantity_g)
    per_serving = recipe_macro_totals_per_serving(meal_entry.recipe)
    servings_eaten = float(meal_entry.servings)
    return {key: round(value * servings_eaten, 2) for key, value in per_serving.items()}
