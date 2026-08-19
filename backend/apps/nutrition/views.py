from rest_framework import viewsets

from . import selectors, services
from .models import FoodItem, MealEntry, NutrientType
from .permissions import FoodItemPermission, MealEntryPermission, NutrientTypePermission
from .serializers import FoodItemSerializer, MealEntrySerializer, NutrientTypeSerializer


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
