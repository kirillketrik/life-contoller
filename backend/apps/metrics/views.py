from datetime import timedelta

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from . import formula_engine, selectors, services
from .aggregation import Timeframe, TimeframeUnit, bucketize, summarize, time_in_range_percent
from .formula_engine.interpreter import evaluate_node
from .formula_engine.resolvers import AsOfResolver
from .models import (
    FavoriteMetric,
    FormulaDefinition,
    MetricEntry,
    MetricImportSettings,
    MetricThreshold,
    MetricType,
    ValueType,
)
from .permissions import (
    FormulaDefinitionPermission,
    MetricEntryPermission,
    MetricThresholdPermission,
    MetricTypePermission,
)
from .serializers import (
    AggregateQuerySerializer,
    BulkImportRequestSerializer,
    FavoriteReorderSerializer,
    FormulaDefinitionSerializer,
    FormulaPreviewSerializer,
    MetricEntrySerializer,
    MetricImportSettingsSerializer,
    MetricThresholdSerializer,
    MetricTypeSerializer,
)

FAVORITE_ACTIONS = {"favorite", "favorites", "reorder_favorites"}
IMPORT_ACTIONS = {"import_settings", "import_preview", "bulk_import"}

DEFAULT_RELATIVE_DAYS = 30


class MetricTypeViewSet(viewsets.ModelViewSet):
    serializer_class = MetricTypeSerializer
    permission_classes = [MetricTypePermission]
    queryset = MetricType.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.metric_type_list()

    def get_permissions(self):
        """Favoriting and bulk-importing entries are personal actions any
        authenticated user takes on their own data, not a role-gated edit of
        the shared MetricType catalog — same ownership-vs-role-gated
        distinction as MetricEntry/MetricThreshold (see
        apps.metrics.permissions), just exposed as actions on this viewset
        instead of a separate one. Ownership itself is enforced by scoping
        every query to `request.user` in the action bodies below, not by an
        object-level permission check."""
        if self.action in FAVORITE_ACTIONS | IMPORT_ACTIONS:
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    @action(detail=True, methods=["post", "delete"], url_path="favorite")
    def favorite(self, request, pk=None):
        """Idempotent: POST when already favorited, or DELETE when not, is a
        no-op rather than an error."""
        metric_type = selectors.metric_type_get(metric_type_id=pk)
        if metric_type is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.method == "POST":
            FavoriteMetric.objects.get_or_create(user=request.user, metric_type=metric_type)
        else:
            FavoriteMetric.objects.filter(user=request.user, metric_type=metric_type).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="favorites")
    def favorites(self, request):
        return Response(selectors.favorites_chart_data_for_user(user=request.user))

    @action(detail=False, methods=["patch"], url_path="favorites/reorder")
    def reorder_favorites(self, request):
        serializer = FavoriteReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        metric_type_ids = serializer.validated_data["metric_type_ids"]

        favorites_by_type = {
            favorite.metric_type_id: favorite
            for favorite in selectors.favorite_metric_list_for_user(user=request.user)
        }
        if set(metric_type_ids) != set(favorites_by_type):
            return Response(
                {"detail": "metric_type_ids must match your current favorites exactly."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for index, metric_type_id in enumerate(metric_type_ids):
            favorite = favorites_by_type[metric_type_id]
            if favorite.order != index:
                favorite.order = index
                favorite.save(update_fields=["order"])
        return Response(selectors.favorites_chart_data_for_user(user=request.user))

    @action(detail=True, methods=["get", "put"], url_path="import-settings")
    def import_settings(self, request, pk=None):
        """The requesting user's saved default bulk-import template for this
        metric type. GET returns `null` (not 404) when none is saved yet —
        the frontend pre-fills the form from it when present and leaves the
        builder empty otherwise. PUT upserts it (create on first save, update
        on every save after)."""
        metric_type = selectors.metric_type_get(metric_type_id=pk)
        if metric_type is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        existing = selectors.metric_import_settings_get_for_user(
            user=request.user, metric_type_id=metric_type.id
        )
        if request.method == "GET":
            if existing is None:
                return Response(None)
            return Response(MetricImportSettingsSerializer(existing).data)

        serializer = MetricImportSettingsSerializer(instance=existing, data=request.data)
        serializer.is_valid(raise_exception=True)
        if existing is None:
            instance = MetricImportSettings.objects.create(
                user=request.user, metric_type=metric_type, **serializer.validated_data
            )
        else:
            instance = serializer.save()
        return Response(MetricImportSettingsSerializer(instance).data)

    def _importable_metric_type_or_error(self, pk):
        metric_type = selectors.metric_type_get(metric_type_id=pk)
        if metric_type is None:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if metric_type.is_computed or metric_type.is_singleton:
            return None, Response(
                {"detail": "Computed and singleton metric types can't be bulk-imported."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return metric_type, None

    @action(detail=True, methods=["post"], url_path="import/preview")
    def import_preview(self, request, pk=None):
        """Resolves what a bulk-import run would do — per-row parsed value,
        recorded_at, and new/duplicate_skip/duplicate_overwrite/invalid
        status — without persisting anything. Shares its resolution logic
        with `bulk_import` below via `services.resolve_bulk_import_items`."""
        metric_type, error = self._importable_metric_type_or_error(pk)
        if error is not None:
            return error

        serializer = BulkImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        results = services.resolve_bulk_import_items(
            metric_type=metric_type,
            user=request.user,
            items=data["items"],
            date_format=data["date_format"],
            decimal_separator=data["decimal_separator"],
            duplicate_policy=data["duplicate_policy"],
        )
        return Response({"items": [item.to_dict() for item in results]})

    @action(detail=True, methods=["post"], url_path="import")
    def bulk_import(self, request, pk=None):
        """Actually creates/overwrites `MetricEntry` rows for a bulk-import
        run. Partial success, same as `resolve_bulk_import_items`'s
        row-by-row statuses: a bad or duplicate-skipped row never blocks the
        rest of the batch."""
        metric_type, error = self._importable_metric_type_or_error(pk)
        if error is not None:
            return error

        serializer = BulkImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        results = services.resolve_bulk_import_items(
            metric_type=metric_type,
            user=request.user,
            items=data["items"],
            date_format=data["date_format"],
            decimal_separator=data["decimal_separator"],
            duplicate_policy=data["duplicate_policy"],
        )
        summary = services.execute_bulk_import(
            metric_type=metric_type, user=request.user, resolved_items=results
        )
        return Response(summary)

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


class FormulaPreviewView(APIView):
    """Validates and, if structurally valid, evaluates a not-yet-saved
    formula expression for the requesting admin's own current data — powers
    both the builder's live preview and the "reject with a clear error
    before saving" requirement, from one endpoint. Admin-only, same as the
    rest of formula-definition editing."""

    permission_classes = [FormulaDefinitionPermission]

    def post(self, request):
        serializer = FormulaPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expression = serializer.validated_data["expression"]
        computed_metric_type_id = serializer.validated_data.get("computed_metric_type")

        errors = formula_engine.validate_expression(
            expression, computed_metric_type_id=computed_metric_type_id
        )
        if errors:
            return Response(
                {"value": None, "errors": [{"code": e.code, "detail": e.detail} for e in errors]}
            )

        node = formula_engine.parse_node(expression)
        value = evaluate_node(node, AsOfResolver(user=request.user, at=timezone.now()))
        return Response({"value": value, "errors": []})


class DashboardSummaryView(APIView):
    """KPI counts + chart-card breakdowns for the dashboard landing page, all
    scoped to the requesting user (personal, like `/aggregate/`)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(selectors.dashboard_summary_for_user(user=request.user))
