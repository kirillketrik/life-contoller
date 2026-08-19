from django.contrib import admin

from .models import FoodItem, FoodNutrientValue, MealEntry, NutrientType


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


@admin.register(MealEntry)
class MealEntryAdmin(admin.ModelAdmin):
    list_display = ["food_item", "owner", "meal_type", "quantity_g", "datetime"]
    list_filter = ["meal_type"]
    search_fields = ["owner__username", "food_item__name"]
    autocomplete_fields = ["owner", "food_item"]
    date_hierarchy = "datetime"
