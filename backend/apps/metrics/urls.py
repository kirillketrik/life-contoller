from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DashboardSummaryView,
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

urlpatterns = [
    path("dashboard-summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    *router.urls,
]
