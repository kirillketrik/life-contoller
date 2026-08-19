from django.conf import settings
from django.db import models


class NutrientCategory(models.TextChoices):
    MACRO = "macro", "Macro"
    MICRO = "micro", "Micro"


class NutrientType(models.Model):
    """An admin-defined kind of nutrient a `FoodItem` can carry a value for
    (e.g. "Vitamin C", "Sodium", "Fiber") — the micronutrient equivalent of
    `apps.metrics.models.MetricType`. Deliberately generic so new nutrients
    are new rows here, not new `FoodItem` columns: only the four macros
    (calories/protein/fat/carbs) are fixed columns on `FoodItem`, since
    they're always needed and always present.

    `is_system` distinguishes the baseline set seeded by `seed_nutrients`
    from ones an admin adds later — informational only, doesn't affect
    permissions (both are admin-only to create/edit/delete, same as any
    `MetricType`).
    """

    name = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=20)
    category = models.CharField(max_length=10, choices=NutrientCategory.choices)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FoodSource(models.TextChoices):
    OWN = "own", "Own"
    EXTERNAL = "external", "External"


class FoodItem(models.Model):
    """A food product a user can log meals against, owned by that user —
    not a shared/global catalog like `MetricType`/`NutrientType`, since two
    users logging "chicken breast" may mean different brands/preparations.

    Macronutrients are fixed columns for fast, always-needed access; every
    other nutrient is a `FoodNutrientValue` row instead of a schema change.

    `source`/`external_id`/`is_verified` exist now (per the model spec) but
    are write-once-at-creation-time and read-only through the API in this
    phase — manually added items are always `own`/verified; a later phase
    (Open Food Facts search) is what actually populates `external`/
    unverified items, server-side, on selection.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="food_items"
    )
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=10, choices=FoodSource.choices, default=FoodSource.OWN)
    external_id = models.CharField(max_length=100, blank=True)
    calories_per_100g = models.DecimalField(max_digits=6, decimal_places=2)
    protein_per_100g = models.DecimalField(max_digits=6, decimal_places=2)
    fat_per_100g = models.DecimalField(max_digits=6, decimal_places=2)
    carbs_per_100g = models.DecimalField(max_digits=6, decimal_places=2)
    is_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.owner})"


class FoodNutrientValue(models.Model):
    """One `NutrientType` amount for one `FoodItem`, per 100g — the join
    table that lets a food item carry arbitrary micronutrient data without a
    schema change, same role `MetricTypeChoice` plays for choice metrics.
    """

    food_item = models.ForeignKey(
        FoodItem, on_delete=models.CASCADE, related_name="nutrient_values"
    )
    nutrient_type = models.ForeignKey(NutrientType, on_delete=models.CASCADE)
    amount_per_100g = models.DecimalField(max_digits=8, decimal_places=3)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["food_item", "nutrient_type"], name="unique_nutrient_value_per_food_item"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.food_item.name}: {self.nutrient_type.name}"


class MealType(models.TextChoices):
    BREAKFAST = "breakfast", "Breakfast"
    LUNCH = "lunch", "Lunch"
    DINNER = "dinner", "Dinner"
    SNACK = "snack", "Snack"


class MealEntry(models.Model):
    """A logged meal — a `FoodItem` consumed at a point in time, owned by the
    logging user (ownership, same as `FoodItem` — not shared).

    `recipe` isn't wired up yet: Phase 4 adds `Recipe` and a `CheckConstraint`
    requiring exactly one of `food_item`/`recipe`; for now every entry logs a
    `FoodItem` directly, so `food_item` is a plain required FK.

    Saving/deleting a `MealEntry` recomputes that day's materialized
    daily-total `MetricEntry` rows (see
    `apps.nutrition.services.recompute_daily_nutrition_metrics`, called from
    `MealEntryViewSet`) — daily nutrition totals are exposed as ordinary
    `MetricType`s, not a parallel stats system, so they get charts/dashboard
    elements/timeframes for free through the existing metrics layer.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_entries"
    )
    datetime = models.DateTimeField()
    meal_type = models.CharField(max_length=10, choices=MealType.choices)
    food_item = models.ForeignKey(FoodItem, on_delete=models.PROTECT, related_name="meal_entries")
    quantity_g = models.DecimalField(max_digits=7, decimal_places=2)
    cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-datetime"]
        verbose_name_plural = "meal entries"
        indexes = [models.Index(fields=["owner", "-datetime"])]

    def __str__(self) -> str:
        return f"{self.food_item.name} @ {self.datetime:%Y-%m-%d %H:%M} ({self.owner})"
