from rest_framework import viewsets

from . import selectors
from .models import MetricEntry, MetricType
from .permissions import MetricEntryPermission, MetricTypePermission
from .serializers import MetricEntrySerializer, MetricTypeSerializer


class MetricTypeViewSet(viewsets.ModelViewSet):
    serializer_class = MetricTypeSerializer
    permission_classes = [MetricTypePermission]
    queryset = MetricType.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.metric_type_list()


class MetricEntryViewSet(viewsets.ModelViewSet):
    serializer_class = MetricEntrySerializer
    permission_classes = [MetricEntryPermission]
    queryset = MetricEntry.objects.none()  # required for router basename inference

    def get_queryset(self):
        metric_type_id = self.request.query_params.get("metric_type")
        return selectors.metric_entry_list_for_user(
            user=self.request.user,
            metric_type_id=int(metric_type_id) if metric_type_id else None,
        )
