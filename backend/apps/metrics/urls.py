from rest_framework.routers import DefaultRouter

from .views import MetricEntryViewSet, MetricTypeViewSet

router = DefaultRouter()
router.register("metric-types", MetricTypeViewSet, basename="metric-type")
router.register("metric-entries", MetricEntryViewSet, basename="metric-entry")

urlpatterns = router.urls
