from datetime import timedelta

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from . import formula_engine, selectors, services
from .aggregation import summarize, time_in_range_percent
from .formula_engine.interpreter import evaluate_node
from .formula_engine.resolvers import AsOfResolver
from .models import (
    DashboardElement,
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
    DashboardElementInputSerializer,
    DashboardElementReorderSerializer,
    FormulaDefinitionSerializer,
    FormulaPreviewSerializer,
    MetricEntrySerializer,
    MetricImportSettingsSerializer,
    MetricThresholdSerializer,
    MetricTypeSerializer,
)

DASHBOARD_ELEMENT_ACTIONS = {"dashboard_element"}
IMPORT_ACTIONS = {"import_settings", "import_preview", "bulk_import"}

DEFAULT_RELATIVE_DAYS = 30


class MetricTypeViewSet(viewsets.ModelViewSet):
    serializer_class = MetricTypeSerializer
    permission_classes = [MetricTypePermission]
    queryset = MetricType.objects.none()  # required for router basename inference

    def get_queryset(self):
        return selectors.metric_type_list()

    def get_permissions(self):
        """Configuring a metric's dashboard elements and bulk-importing
        entries are personal actions any authenticated user takes on their
        own data, not a role-gated edit of the shared MetricType catalog —
        same ownership-vs-role-gated distinction as MetricEntry/
        MetricThreshold (see apps.metrics.permissions), just exposed as
        actions on this viewset instead of a separate one. Ownership itself
        is enforced by scoping every query to `request.user` in the action
        bodies below, not by an object-level permission check."""
        if self.action in DASHBOARD_ELEMENT_ACTIONS | IMPORT_ACTIONS:
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    @action(detail=True, methods=["post", "patch", "delete"], url_path="dashboard-element")
    def dashboard_element(self, request, pk=None):
        """The requesting user's dashboard configuration for this metric
        type: which elements (chart/current/max/min/avg) are shown and over
        what timeframe. POST/PATCH upsert (create on first save, update on
        every save after) and return the saved config with its resolved
        stats attached; DELETE removes it from the dashboard entirely
        (idempotent — a no-op, not an error, when none exists), which is the
        only way to "turn off" every element, see
        DashboardElementInputSerializer."""
        metric_type = selectors.metric_type_get(metric_type_id=pk)
        if metric_type is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        existing = selectors.dashboard_element_get_for_user(
            user=request.user, metric_type_id=metric_type.id
        )
        if request.method == "DELETE":
            if existing is not None:
                existing.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = DashboardElementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if existing is None:
            instance = DashboardElement.objects.create(
                user=request.user, metric_type=metric_type, **data
            )
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            existing.save()
            instance = existing
        return Response(
            selectors.dashboard_element_data(element=instance, at=timezone.now())
        )

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
        """Raw point series + summary + time-in-range for this metric type,
        for the current user, over a timeframe. Works the same for computed
        metric types (evaluated on the fly) as for regular ones."""
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
        summary = summarize(points)

        threshold = selectors.metric_threshold_get_for_user(
            user=request.user, metric_type_id=metric_type.id
        )
        time_in_range = None
        if threshold is not None:
            time_in_range = time_in_range_percent(
                points, lower_bound=threshold.lower_bound, upper_bound=threshold.upper_bound
            )

        period_changes = selectors.period_changes_for_metric_type(
            metric_type=metric_type, user=request.user, at=range_end
        )
        # Always the single latest entry as of now — deliberately not
        # range_end, so "current" stays correct even when the selected
        # range's end is historical (e.g. a custom range in the past).
        current_value = selectors.current_value_for_metric_type(
            metric_type=metric_type, user=request.user, at=timezone.now()
        )

        return Response(
            {
                "metric_type": metric_type.id,
                "range_start": range_start.isoformat(),
                "range_end": range_end.isoformat(),
                "timeframe_unit": data["timeframe_unit"],
                "timeframe_count": data["timeframe_count"],
                "current": current_value,
                "points": [
                    {"timestamp": point.recorded_at.isoformat(), "value": point.value}
                    for point in sorted(points, key=lambda p: p.recorded_at)
                ],
                "summary": {
                    "min": summary.min,
                    "max": summary.max,
                    "avg": summary.avg,
                    "count": summary.count,
                },
                "time_in_range_percent": time_in_range,
                "threshold": (
                    {"lower_bound": threshold.lower_bound, "upper_bound": threshold.upper_bound}
                    if threshold is not None
                    else None
                ),
                "period_changes": period_changes,
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


class DashboardElementListView(APIView):
    """Every configured dashboard element for the requesting user, each with
    its resolved stats — one request for the whole dashboard, not one
    `/aggregate/`-style request per block (same N+1 concern the old
    favorites endpoint was built to avoid)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            selectors.dashboard_elements_data_for_user(user=request.user, at=timezone.now())
        )


class DashboardElementReorderView(APIView):
    """Persists a new `order` for an exact-match set of the user's own
    dashboard elements — same validate-then-reassign shape as the old
    favorites reorder endpoint it replaces."""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        serializer = DashboardElementReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        metric_type_ids = serializer.validated_data["metric_type_ids"]

        elements_by_type = {
            element.metric_type_id: element
            for element in selectors.dashboard_element_list_for_user(user=request.user)
        }
        if set(metric_type_ids) != set(elements_by_type):
            return Response(
                {"detail": "metric_type_ids must match your current dashboard elements exactly."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for index, metric_type_id in enumerate(metric_type_ids):
            element = elements_by_type[metric_type_id]
            if element.order != index:
                element.order = index
                element.save(update_fields=["order"])
        return Response(
            selectors.dashboard_elements_data_for_user(user=request.user, at=timezone.now())
        )
