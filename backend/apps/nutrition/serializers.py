from rest_framework import serializers

from . import selectors, services
from .models import (
    FoodItem,
    FoodNutrientValue,
    MealEntry,
    MealPlanEntry,
    NutrientType,
    Recipe,
    RecipeIngredient,
)


class NutrientTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NutrientType
        fields = ["id", "name", "unit", "category", "is_system", "created_at"]
        read_only_fields = ["id", "is_system", "created_at"]


class FoodNutrientValueSerializer(serializers.ModelSerializer):
    nutrient_type_name = serializers.CharField(source="nutrient_type.name", read_only=True)
    nutrient_type_unit = serializers.CharField(source="nutrient_type.unit", read_only=True)

    class Meta:
        model = FoodNutrientValue
        fields = [
            "id",
            "nutrient_type",
            "nutrient_type_name",
            "nutrient_type_unit",
            "amount_per_100g",
        ]
        read_only_fields = ["id"]


class FoodItemSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    nutrient_values = FoodNutrientValueSerializer(many=True, required=False)

    class Meta:
        model = FoodItem
        fields = [
            "id",
            "owner",
            "name",
            "brand",
            "source",
            "external_id",
            "calories_per_100g",
            "protein_per_100g",
            "fat_per_100g",
            "carbs_per_100g",
            "is_verified",
            "created_at",
            "updated_at",
            "nutrient_values",
        ]
        # Manually adding/editing a food item always produces an own,
        # verified item — source/external_id/is_verified only ever get set
        # by the (not-yet-built) external-search import path, server-side.
        read_only_fields = [
            "id",
            "owner",
            "source",
            "external_id",
            "is_verified",
            "created_at",
            "updated_at",
        ]

    def validate_nutrient_values(self, value):
        nutrient_type_ids = [item["nutrient_type"].id for item in value]
        if len(nutrient_type_ids) != len(set(nutrient_type_ids)):
            raise serializers.ValidationError(
                "Each nutrient type may only be set once per food item."
            )
        return value

    def create(self, validated_data):
        nutrient_values_data = validated_data.pop("nutrient_values", [])
        return services.create_food_item_with_nutrients(
            validated_data=validated_data,
            nutrient_values_data=nutrient_values_data,
            user=self.context["request"].user,
        )

    def update(self, instance, validated_data):
        nutrient_values_data = validated_data.pop("nutrient_values", None)
        instance = super().update(instance, validated_data)
        if nutrient_values_data is not None:
            services.update_food_item_nutrients(
                food_item=instance, nutrient_values_data=nutrient_values_data
            )
        return instance


class RecipeIngredientSerializer(serializers.ModelSerializer):
    food_item_name = serializers.CharField(source="food_item.name", read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = ["id", "food_item", "food_item_name", "quantity_g"]
        read_only_fields = ["id"]


class RecipeSerializer(serializers.ModelSerializer):
    """A recipe's nutrient totals (whole-recipe and per-serving) are always
    computed from `ingredients` — see `selectors.recipe_macro_totals` — never
    stored, so they can't drift out of sync with the ingredients that back
    them. Each `get_*` method calls that selector independently, but since
    `ingredients__food_item` is prefetched by `selectors.recipe_list_for_user`,
    every call after the first reuses Django's prefetch cache rather than
    re-querying."""

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    ingredients = RecipeIngredientSerializer(many=True, required=False)
    total_calories = serializers.SerializerMethodField()
    total_protein = serializers.SerializerMethodField()
    total_fat = serializers.SerializerMethodField()
    total_carbs = serializers.SerializerMethodField()
    calories_per_serving = serializers.SerializerMethodField()
    protein_per_serving = serializers.SerializerMethodField()
    fat_per_serving = serializers.SerializerMethodField()
    carbs_per_serving = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = [
            "id",
            "owner",
            "name",
            "servings",
            "cost",
            "ingredients",
            "total_calories",
            "total_protein",
            "total_fat",
            "total_carbs",
            "calories_per_serving",
            "protein_per_serving",
            "fat_per_serving",
            "carbs_per_serving",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def validate_ingredients(self, value):
        if not value:
            raise serializers.ValidationError("A recipe needs at least one ingredient.")
        user = self.context["request"].user
        for item in value:
            if item["food_item"].owner_id != user.id:
                raise serializers.ValidationError(
                    "You can only use your own food items as recipe ingredients."
                )
        return value

    def get_total_calories(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals(obj)["calories"]

    def get_total_protein(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals(obj)["protein"]

    def get_total_fat(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals(obj)["fat"]

    def get_total_carbs(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals(obj)["carbs"]

    def get_calories_per_serving(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals_per_serving(obj)["calories"]

    def get_protein_per_serving(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals_per_serving(obj)["protein"]

    def get_fat_per_serving(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals_per_serving(obj)["fat"]

    def get_carbs_per_serving(self, obj: Recipe) -> float:
        return selectors.recipe_macro_totals_per_serving(obj)["carbs"]

    def create(self, validated_data):
        ingredients_data = validated_data.pop("ingredients", [])
        return services.create_recipe_with_ingredients(
            validated_data=validated_data,
            ingredients_data=ingredients_data,
            user=self.context["request"].user,
        )

    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop("ingredients", None)
        instance = super().update(instance, validated_data)
        if ingredients_data is not None:
            services.update_recipe_ingredients(recipe=instance, ingredients_data=ingredients_data)
        return instance


class ExactlyOneOfFoodOrRecipeMixin:
    """Shared `validate()` for a serializer whose model has `food_item`/
    `recipe` (exactly one set) plus `quantity_g`/`servings` — `MealEntry` and
    `MealPlanEntry` both follow this shape, so the ownership/exactly-one/
    positive-amount rule lives here once rather than risking the two
    drifting apart."""

    def validate(self, attrs):
        food_item = attrs.get("food_item", getattr(self.instance, "food_item", None))
        recipe = attrs.get("recipe", getattr(self.instance, "recipe", None))
        if bool(food_item) == bool(recipe):
            raise serializers.ValidationError(
                "Provide exactly one of food_item or recipe, not both or neither."
            )

        user = self.context["request"].user
        if food_item is not None and food_item.owner_id != user.id:
            raise serializers.ValidationError(
                {"food_item": "You can only use your own food items."}
            )
        if recipe is not None and recipe.owner_id != user.id:
            raise serializers.ValidationError({"recipe": "You can only use your own recipes."})

        quantity_g = attrs.get("quantity_g", getattr(self.instance, "quantity_g", None))
        servings = attrs.get("servings", getattr(self.instance, "servings", None))
        if food_item is not None and (quantity_g is None or quantity_g <= 0):
            raise serializers.ValidationError({"quantity_g": "Quantity must be greater than zero."})
        if recipe is not None and (servings is None or servings <= 0):
            raise serializers.ValidationError({"servings": "Servings must be greater than zero."})
        return attrs

    def create(self, validated_data):
        validated_data.setdefault("owner", self.context["request"].user)
        return super().create(validated_data)


class MealEntrySerializer(ExactlyOneOfFoodOrRecipeMixin, serializers.ModelSerializer):
    """`calories`/`protein`/`fat`/`carbs` are computed via
    `selectors.meal_entry_macro_totals`, which works uniformly whether this
    entry logs a `FoodItem` directly or a `Recipe` — never stored, same
    "computed property, not a duplicated value" rule `FoodItem`/`Recipe`
    already follow, so they can never drift out of sync with whichever item
    they reference.

    Exactly one of `food_item`/`recipe` must be set (enforced by
    `ExactlyOneOfFoodOrRecipeMixin.validate`, mirrored by the model's
    `mealentry_exactly_one_of_food_or_recipe` `CheckConstraint` — same
    defense-in-depth pattern used elsewhere in this app): `quantity_g` is
    required for a food-item entry, `servings` for a recipe entry."""

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    food_item_name = serializers.SerializerMethodField()
    recipe_name = serializers.SerializerMethodField()
    calories = serializers.SerializerMethodField()
    protein = serializers.SerializerMethodField()
    fat = serializers.SerializerMethodField()
    carbs = serializers.SerializerMethodField()

    class Meta:
        model = MealEntry
        fields = [
            "id",
            "owner",
            "datetime",
            "meal_type",
            "food_item",
            "food_item_name",
            "recipe",
            "recipe_name",
            "quantity_g",
            "servings",
            "cost",
            "calories",
            "protein",
            "fat",
            "carbs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def get_food_item_name(self, obj: MealEntry) -> str | None:
        return obj.food_item.name if obj.food_item_id else None

    def get_recipe_name(self, obj: MealEntry) -> str | None:
        return obj.recipe.name if obj.recipe_id else None

    def get_calories(self, obj: MealEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["calories"]

    def get_protein(self, obj: MealEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["protein"]

    def get_fat(self, obj: MealEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["fat"]

    def get_carbs(self, obj: MealEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["carbs"]


class MealPlanEntrySerializer(ExactlyOneOfFoodOrRecipeMixin, serializers.ModelSerializer):
    """The "schedule ahead" counterpart to `MealEntrySerializer` — same
    exactly-one-of-food-or-recipe rule (via the shared mixin), same computed
    calorie/macro preview (`selectors.meal_entry_macro_totals` works
    unmodified here, see its docstring), but keyed by `date` instead of
    `datetime`. `is_eaten`/`resulting_meal_entry` are read-only: the only way
    to set them is `POST .../mark-eaten/` (`MealPlanEntryViewSet.mark_eaten`
    → `services.mark_meal_plan_entry_eaten`), never a plain `PATCH` — marking
    a plan eaten has a real side effect (creating a `MealEntry` and
    recomputing that day's totals) that a generic field update shouldn't be
    able to trigger implicitly."""

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    food_item_name = serializers.SerializerMethodField()
    recipe_name = serializers.SerializerMethodField()
    calories = serializers.SerializerMethodField()
    protein = serializers.SerializerMethodField()
    fat = serializers.SerializerMethodField()
    carbs = serializers.SerializerMethodField()
    is_eaten = serializers.SerializerMethodField()

    class Meta:
        model = MealPlanEntry
        fields = [
            "id",
            "owner",
            "date",
            "meal_type",
            "food_item",
            "food_item_name",
            "recipe",
            "recipe_name",
            "quantity_g",
            "servings",
            "calories",
            "protein",
            "fat",
            "carbs",
            "is_eaten",
            "resulting_meal_entry",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "is_eaten",
            "resulting_meal_entry",
            "created_at",
            "updated_at",
        ]

    def get_food_item_name(self, obj: MealPlanEntry) -> str | None:
        return obj.food_item.name if obj.food_item_id else None

    def get_recipe_name(self, obj: MealPlanEntry) -> str | None:
        return obj.recipe.name if obj.recipe_id else None

    def get_calories(self, obj: MealPlanEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["calories"]

    def get_protein(self, obj: MealPlanEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["protein"]

    def get_fat(self, obj: MealPlanEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["fat"]

    def get_carbs(self, obj: MealPlanEntry) -> float:
        return selectors.meal_entry_macro_totals(obj)["carbs"]

    def get_is_eaten(self, obj: MealPlanEntry) -> bool:
        return obj.resulting_meal_entry_id is not None


class DuplicateMealPlanDaySerializer(serializers.Serializer):
    """Input for `MealPlanEntryViewSet.duplicate_day` — just the two dates,
    validated as plain `DateField`s. No model behind this one, same
    "un-modeled action input" shape a plain `serializers.Serializer` is for."""

    source_date = serializers.DateField()
    target_date = serializers.DateField()
