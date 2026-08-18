from rest_framework.routers import DefaultRouter

from .views import (
    FormulaDefinitionViewSet,
    MetricEntryViewSet,
    MetricThresholdViewSet,
    MetricTypeViewSet,
)

router = DefaultRouter()
router.register("metric-types", MetricTypeViewSet, basename="metric-type")
router.register("metric-entries", MetricEntryViewSet, basename="metric-entry")
router.register("metric-thresholds", MetricThresholdViewSet, basename="metric-threshold")
router.register("formula-definitions", FormulaDefinitionViewSet, basename="formula-definition")

urlpatterns = router.urls
