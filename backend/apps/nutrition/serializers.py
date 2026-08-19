from rest_framework import serializers

from . import services
from .models import FoodItem, FoodNutrientValue, MealEntry, NutrientType


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


class MealEntrySerializer(serializers.ModelSerializer):
    """`calories`/`protein`/`fat`/`carbs` are computed from the linked
    `FoodItem`'s per-100g values × `quantity_g`, not stored — same
    "computed property, not a stored/duplicated value" rule `CLAUDE.md` calls
    out for `Recipe`/`MealEntry` nutrient totals, so they can never drift out
    of sync with the food item they reference."""

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    food_item_name = serializers.CharField(source="food_item.name", read_only=True)
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
            "quantity_g",
            "cost",
            "calories",
            "protein",
            "fat",
            "carbs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def _nutrient_total(self, obj: MealEntry, per_100g) -> float:
        return round(float(per_100g) * float(obj.quantity_g) / 100, 2)

    def get_calories(self, obj: MealEntry) -> float:
        return self._nutrient_total(obj, obj.food_item.calories_per_100g)

    def get_protein(self, obj: MealEntry) -> float:
        return self._nutrient_total(obj, obj.food_item.protein_per_100g)

    def get_fat(self, obj: MealEntry) -> float:
        return self._nutrient_total(obj, obj.food_item.fat_per_100g)

    def get_carbs(self, obj: MealEntry) -> float:
        return self._nutrient_total(obj, obj.food_item.carbs_per_100g)

    def validate(self, attrs):
        food_item = attrs.get("food_item") or getattr(self.instance, "food_item", None)
        user = self.context["request"].user
        if food_item is not None and food_item.owner_id != user.id:
            raise serializers.ValidationError(
                {"food_item": "You can only log meals against your own food items."}
            )
        quantity_g = attrs.get("quantity_g", getattr(self.instance, "quantity_g", None))
        if quantity_g is not None and quantity_g <= 0:
            raise serializers.ValidationError({"quantity_g": "Quantity must be greater than zero."})
        return attrs

    def create(self, validated_data):
        validated_data.setdefault("owner", self.context["request"].user)
        return super().create(validated_data)
