from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import selectors, services
from .models import FoodItem, MealEntry, MealPlanEntry, NutrientType, Recipe
from .permissions import (
    FoodItemPermission,
    MealEntryPermission,
    MealPlanEntryPermission,
    NutrientTypePermission,
    RecipePermission,
)
from .serializers import (
    FoodItemSerializer,
    MealEntrySerializer,
    MealPlanEntrySerializer,
    NutrientTypeSerializer,
    RecipeSerializer,
)


class NutrientTypeViewSet(viewsets.ModelViewSet):
    serializer_class = NutrientTypeSerializer
    permission_classes = [NutrientTypePermission]
    queryset = NutrientType.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.nutrient_type_list()


class FoodItemViewSet(viewsets.ModelViewSet):
    serializer_class = FoodItemSerializer
    permission_classes = [FoodItemPermission]
    queryset = FoodItem.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.food_item_list_for_user(
            user=self.request.user, search=self.request.query_params.get("search")
        )


class RecipeViewSet(viewsets.ModelViewSet):
    serializer_class = RecipeSerializer
    permission_classes = [RecipePermission]
    queryset = Recipe.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.recipe_list_for_user(
            user=self.request.user, search=self.request.query_params.get("search")
        )


class MealEntryViewSet(viewsets.ModelViewSet):
    """Logging a meal (create/update/delete) recomputes that day's
    materialized daily-total `MetricEntry` rows — see
    `services.recompute_daily_nutrition_metrics`. An update recomputes both
    the entry's date before and after the save, in case the date itself
    changed."""

    serializer_class = MealEntrySerializer
    permission_classes = [MealEntryPermission]
    queryset = MealEntry.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.meal_entry_list_for_user(
            user=self.request.user, entry_date=self.request.query_params.get("date")
        )

    def perform_create(self, serializer):
        instance = serializer.save()
        services.recompute_daily_nutrition_metrics(
            user=instance.owner, entry_date=instance.datetime.date()
        )

    def perform_update(self, serializer):
        old_date = serializer.instance.datetime.date()
        instance = serializer.save()
        new_date = instance.datetime.date()
        services.recompute_daily_nutrition_metrics(user=instance.owner, entry_date=old_date)
        if new_date != old_date:
            services.recompute_daily_nutrition_metrics(user=instance.owner, entry_date=new_date)

    def perform_destroy(self, instance):
        user = instance.owner
        entry_date = instance.datetime.date()
        instance.delete()
        services.recompute_daily_nutrition_metrics(user=user, entry_date=entry_date)


class MealPlanEntryViewSet(viewsets.ModelViewSet):
    """Planned meals — ownership-scoped like `MealEntryViewSet`, but a plan
    by itself never touches the daily-total materialization: only the
    `mark_eaten` action does, by creating a real `MealEntry` (which goes
    through the normal `MealEntryViewSet`-equivalent recompute)."""

    serializer_class = MealPlanEntrySerializer
    permission_classes = [MealPlanEntryPermission]
    queryset = MealPlanEntry.objects.none()  # required for router basename inference

    def get_queryset(self):
        params = self.request.query_params
        return selectors.meal_plan_entry_list_for_user(
            user=self.request.user,
            date=params.get("date"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        )

    @action(detail=True, methods=["post"], url_path="mark-eaten")
    def mark_eaten(self, request, pk=None):
        plan_entry = self.get_object()
        try:
            services.mark_meal_plan_entry_eaten(plan_entry=plan_entry)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        plan_entry.refresh_from_db()
        serializer = self.get_serializer(plan_entry)
        return Response(serializer.data)
