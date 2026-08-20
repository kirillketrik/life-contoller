from django.contrib import admin

from .models import FoodItem, FoodNutrientValue, MealEntry, NutrientType, Recipe, RecipeIngredient


@admin.register(NutrientType)
class NutrientTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "unit", "category", "is_system"]
    list_filter = ["category", "is_system"]
    search_fields = ["name"]


class FoodNutrientValueInline(admin.TabularInline):
    model = FoodNutrientValue
    extra = 0
    autocomplete_fields = ["nutrient_type"]


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "brand",
        "owner",
        "source",
        "calories_per_100g",
        "protein_per_100g",
        "fat_per_100g",
        "carbs_per_100g",
        "is_verified",
    ]
    list_filter = ["source", "is_verified"]
    search_fields = ["name", "brand", "owner__username"]
    autocomplete_fields = ["owner"]
    inlines = [FoodNutrientValueInline]


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0
    autocomplete_fields = ["food_item"]


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "servings", "cost"]
    search_fields = ["name", "owner__username"]
    autocomplete_fields = ["owner"]
    inlines = [RecipeIngredientInline]


@admin.register(MealEntry)
class MealEntryAdmin(admin.ModelAdmin):
    list_display = [
        "food_item",
        "recipe",
        "owner",
        "meal_type",
        "quantity_g",
        "servings",
        "datetime",
    ]
    list_filter = ["meal_type"]
    search_fields = ["owner__username", "food_item__name", "recipe__name"]
    autocomplete_fields = ["owner", "food_item", "recipe"]
    date_hierarchy = "datetime"
