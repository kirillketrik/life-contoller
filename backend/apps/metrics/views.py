from datetime import timedelta

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from . import selectors
from .aggregation import Timeframe, TimeframeUnit, bucketize, summarize, time_in_range_percent
from .models import FormulaDefinition, MetricEntry, MetricThreshold, MetricType, ValueType
from .permissions import (
    FormulaDefinitionPermission,
    MetricEntryPermission,
    MetricThresholdPermission,
    MetricTypePermission,
)
from .serializers import (
    AggregateQuerySerializer,
    FormulaDefinitionSerializer,
    MetricEntrySerializer,
    MetricThresholdSerializer,
    MetricTypeSerializer,
)

DEFAULT_RELATIVE_DAYS = 30


class MetricTypeViewSet(viewsets.ModelViewSet):
    serializer_class = MetricTypeSerializer
    permission_classes = [MetricTypePermission]
    queryset = MetricType.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.metric_type_list()

    @action(detail=True, methods=["get"])
    def aggregate(self, request, pk=None):
        """OHLC-bucketed series + summary + time-in-range for this metric
        type, for the current user, over a timeframe. Works the same for
        computed metric types (evaluated on the fly) as for regular ones."""
        metric_type = selectors.metric_type_get(metric_type_id=pk)
        if metric_type is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not metric_type.is_computed and metric_type.value_type != ValueType.NUMBER:
            return Response(
                {"detail": "Only number-valued or computed metric types can be aggregated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        query = AggregateQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        range_end = data.get("end") or timezone.now()
        range_start = data.get("start") or range_end - timedelta(
            days=data.get("relative_days", DEFAULT_RELATIVE_DAYS)
        )

        points = selectors.points_for_metric_type(
            metric_type=metric_type,
            user=request.user,
            range_start=range_start,
            range_end=range_end,
        )
        timeframe = Timeframe(
            unit=TimeframeUnit(data["timeframe_unit"]), count=data["timeframe_count"]
        )
        buckets = bucketize(points, timeframe, range_start)
        summary = summarize(points)

        threshold = selectors.metric_threshold_get_for_user(
            user=request.user, metric_type_id=metric_type.id
        )
        time_in_range = None
        if threshold is not None:
            time_in_range = time_in_range_percent(
                points, lower_bound=threshold.lower_bound, upper_bound=threshold.upper_bound
            )

        return Response(
            {
                "metric_type": metric_type.id,
                "range_start": range_start.isoformat(),
                "range_end": range_end.isoformat(),
                "timeframe_unit": timeframe.unit.value,
                "timeframe_count": timeframe.count,
                "buckets": [
                    {
                        "bucket_start": bucket.bucket_start.isoformat(),
                        "open": bucket.open,
                        "high": bucket.high,
                        "low": bucket.low,
                        "close": bucket.close,
                        "count": bucket.count,
                    }
                    for bucket in buckets
                ],
                "summary": {
                    "min": summary.min,
                    "max": summary.max,
                    "avg": summary.avg,
                    "count": summary.count,
                },
                "time_in_range_percent": time_in_range,
            }
        )


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


class MetricThresholdViewSet(viewsets.ModelViewSet):
    serializer_class = MetricThresholdSerializer
    permission_classes = [MetricThresholdPermission]
    queryset = MetricThreshold.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.metric_threshold_list_for_user(user=self.request.user)


class FormulaDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = FormulaDefinitionSerializer
    permission_classes = [FormulaDefinitionPermission]
    queryset = FormulaDefinition.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.formula_definition_list()


class DashboardSummaryView(APIView):
    """KPI counts + chart-card breakdowns for the dashboard landing page, all
    scoped to the requesting user (personal, like `/aggregate/`)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(selectors.dashboard_summary_for_user(user=request.user))
