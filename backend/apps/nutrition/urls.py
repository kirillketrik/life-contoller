from rest_framework.routers import DefaultRouter

from .views import FoodItemViewSet, MealEntryViewSet, NutrientTypeViewSet

router = DefaultRouter()
router.register("nutrient-types", NutrientTypeViewSet, basename="nutrient-type")
router.register("food-items", FoodItemViewSet, basename="food-item")
router.register("meal-entries", MealEntryViewSet, basename="meal-entry")

urlpatterns = router.urls
