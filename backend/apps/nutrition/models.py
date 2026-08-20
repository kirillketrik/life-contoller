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


class Recipe(models.Model):
    """A reusable "dish" — a named combination of `FoodItem`s with
    quantities, owned by the user who built it (ownership, same as
    `FoodItem` — not shared). Nutrient totals (whole-recipe and per-serving)
    are always computed from `ingredients` at read time (see
    `selectors.recipe_macro_totals`), never stored on the row, so they can
    never drift out of sync with the ingredients that back them — same
    "computed property, not a duplicated value" rule `FoodItem`/`MealEntry`
    already follow.

    `servings` is how many servings the *whole* recipe yields (e.g. "this
    soup makes 4 bowls"), not how much any one `MealEntry` logs — a
    `MealEntry.servings` of `1.5` against this recipe means "one and a half
    of those bowls," independent of how many the recipe was originally
    divided into.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipes"
    )
    name = models.CharField(max_length=255)
    servings = models.PositiveIntegerField(default=1)
    cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.owner})"


class RecipeIngredient(models.Model):
    """One `FoodItem` and its quantity within a `Recipe` — the join table
    that lets a recipe be an arbitrary-length "union of products," same role
    `FoodNutrientValue` plays for a food item's micronutrients.
    `on_delete=PROTECT` on `food_item` mirrors `MealEntry.food_item`: a food
    item in active use (here, as a recipe ingredient) can't be silently
    deleted out from under it.
    """

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    food_item = models.ForeignKey(
        FoodItem, on_delete=models.PROTECT, related_name="recipe_ingredients"
    )
    quantity_g = models.DecimalField(max_digits=7, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.food_item.name} in {self.recipe.name}"


class MealType(models.TextChoices):
    BREAKFAST = "breakfast", "Breakfast"
    LUNCH = "lunch", "Lunch"
    DINNER = "dinner", "Dinner"
    SNACK = "snack", "Snack"


class MealEntry(models.Model):
    """A logged meal — either a `FoodItem` or a `Recipe` consumed at a point
    in time, owned by the logging user (ownership, same as `FoodItem` — not
    shared). Exactly one of `food_item`/`recipe` is set, enforced by the
    `mealentry_exactly_one_of_food_or_recipe` `CheckConstraint` below (and
    again in `MealEntrySerializer.validate`, same defense-in-depth pattern
    used elsewhere in this app): `quantity_g` is how the amount is expressed
    for a `FoodItem` entry, `servings` for a `Recipe` entry — the other stays
    null in either case.

    Saving/deleting a `MealEntry` recomputes that day's materialized
    daily-total `MetricEntry` rows (see
    `apps.nutrition.services.recompute_daily_nutrition_metrics`, called from
    `MealEntryViewSet`) — daily nutrition totals are exposed as ordinary
    `MetricType`s, not a parallel stats system, so they get charts/dashboard
    elements/timeframes for free through the existing metrics layer. This
    works identically for a recipe-based entry, since the materialization
    sums `selectors.meal_entry_macro_totals`, not the food item directly.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_entries"
    )
    datetime = models.DateTimeField()
    meal_type = models.CharField(max_length=10, choices=MealType.choices)
    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.PROTECT,
        related_name="meal_entries",
        null=True,
        blank=True,
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.PROTECT, related_name="meal_entries", null=True, blank=True
    )
    quantity_g = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    servings = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-datetime"]
        verbose_name_plural = "meal entries"
        indexes = [models.Index(fields=["owner", "-datetime"])]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(food_item__isnull=False, recipe__isnull=True)
                    | models.Q(food_item__isnull=True, recipe__isnull=False)
                ),
                name="mealentry_exactly_one_of_food_or_recipe",
            )
        ]

    def __str__(self) -> str:
        item_name = self.food_item.name if self.food_item_id else self.recipe.name
        return f"{item_name} @ {self.datetime:%Y-%m-%d %H:%M} ({self.owner})"
