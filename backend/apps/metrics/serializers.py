from datetime import date

from rest_framework import serializers

from . import formula_engine, services
from .aggregation import TimeframeUnit
from .models import (
    DashboardTimeframe,
    FormulaDefinition,
    MetricEntry,
    MetricImportSettings,
    MetricThreshold,
    MetricType,
    MetricTypeChoice,
    ValueType,
)


class MetricTypeChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricTypeChoice
        fields = ["id", "code", "label", "numeric_value", "order"]
        read_only_fields = ["id"]


class MetricTypeSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    choices = MetricTypeChoiceSerializer(many=True, required=False)

    class Meta:
        model = MetricType
        fields = [
            "id",
            "name",
            "unit",
            "value_type",
            "aggregation",
            "is_computed",
            "is_singleton",
            "created_by",
            "created_at",
            "updated_at",
            "choices",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        value_type = attrs.get("value_type") or getattr(self.instance, "value_type", None)
        choices = attrs.get("choices")
        if value_type == ValueType.CHOICE:
            if not choices:
                raise serializers.ValidationError(
                    {"choices": "A choice metric type needs at least one option."}
                )
            codes = [choice["code"] for choice in choices]
            if len(codes) != len(set(codes)):
                raise serializers.ValidationError({"choices": "Option codes must be unique."})
        return attrs

    def create(self, validated_data):
        choices_data = validated_data.pop("choices", [])
        return services.create_metric_type_with_choices(
            validated_data=validated_data,
            choices_data=choices_data,
            user=self.context["request"].user,
        )

    def update(self, instance, validated_data):
        choices_data = validated_data.pop("choices", None)
        instance = super().update(instance, validated_data)
        if choices_data is not None:
            services.update_metric_type_choices(metric_type=instance, choices_data=choices_data)
        return instance


class MetricEntrySerializer(serializers.ModelSerializer):
    metric_type_name = serializers.CharField(source="metric_type.name", read_only=True)
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = MetricEntry
        fields = [
            "id",
            "metric_type",
            "metric_type_name",
            "owner",
            "value",
            "context",
            "recorded_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data.setdefault("owner", self.context["request"].user)
        return super().create(validated_data)

    def validate(self, attrs):
        metric_type = attrs.get("metric_type") or getattr(self.instance, "metric_type", None)
        value = attrs.get("value", getattr(self.instance, "value", None))
        if metric_type is not None and metric_type.is_computed:
            raise serializers.ValidationError(
                {
                    "metric_type": (
                        "Computed metric types are derived automatically and can't have "
                        "entries logged directly."
                    )
                }
            )
        if metric_type is not None and metric_type.is_singleton and self.instance is None:
            owner = self.context["request"].user
            if MetricEntry.objects.filter(metric_type=metric_type, owner=owner).exists():
                raise serializers.ValidationError(
                    {
                        "metric_type": (
                            "This metric type only holds a single value — edit the existing "
                            "entry instead of creating a new one."
                        )
                    }
                )
        if metric_type is not None and value is not None:
            self._validate_value_matches_type(metric_type, value)
        return attrs

    @staticmethod
    def _validate_value_matches_type(metric_type, value) -> None:
        expectations = {
            ValueType.NUMBER: (int, float),
            ValueType.BOOLEAN: bool,
            ValueType.TEXT: str,
            ValueType.DATE: str,
            ValueType.CHOICE: str,
        }
        expected = expectations.get(metric_type.value_type)
        if expected is None:
            return
        # bool is a subclass of int in Python; keep number/boolean mutually exclusive.
        if metric_type.value_type == ValueType.NUMBER and isinstance(value, bool):
            raise serializers.ValidationError(
                {"value": "Expected a number for this metric type."}
            )
        if not isinstance(value, expected):
            raise serializers.ValidationError(
                {"value": f"Expected a {metric_type.value_type} value for this metric type."}
            )
        if metric_type.value_type == ValueType.DATE:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"value": "Expected an ISO date string (YYYY-MM-DD) for this metric type."}
                ) from exc
        if metric_type.value_type == ValueType.CHOICE:
            valid_codes = set(metric_type.choices.values_list("code", flat=True))
            if value not in valid_codes:
                raise serializers.ValidationError(
                    {"value": f"'{value}' is not a valid option for this metric type."}
                )


class MetricThresholdSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = MetricThreshold
        fields = [
            "id",
            "metric_type",
            "user",
            "lower_bound",
            "upper_bound",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def validate(self, attrs):
        lower_bound = attrs.get("lower_bound", getattr(self.instance, "lower_bound", None))
        upper_bound = attrs.get("upper_bound", getattr(self.instance, "upper_bound", None))
        if lower_bound is None and upper_bound is None:
            raise serializers.ValidationError("Set at least one of lower_bound / upper_bound.")
        if lower_bound is not None and upper_bound is not None and lower_bound > upper_bound:
            raise serializers.ValidationError("lower_bound must not be greater than upper_bound.")

        metric_type = attrs.get("metric_type") or getattr(self.instance, "metric_type", None)
        user = self.context["request"].user
        existing = MetricThreshold.objects.filter(user=user, metric_type=metric_type)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if metric_type is not None and existing.exists():
            raise serializers.ValidationError(
                "A threshold for this metric type already exists — edit it instead."
            )
        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class FormulaDefinitionSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = FormulaDefinition
        fields = [
            "id",
            "computed_metric_type",
            "expression",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        computed_metric_type = attrs.get("computed_metric_type") or getattr(
            self.instance, "computed_metric_type", None
        )
        if computed_metric_type is not None and not computed_metric_type.is_computed:
            raise serializers.ValidationError(
                {"computed_metric_type": "Must be a MetricType with is_computed=True."}
            )

        expression = attrs.get("expression", getattr(self.instance, "expression", None))
        if expression is not None:
            errors = formula_engine.validate_expression(
                expression,
                computed_metric_type_id=computed_metric_type.id if computed_metric_type else None,
            )
            if errors:
                raise serializers.ValidationError(
                    {
                        "expression": [
                            {"code": error.code, "detail": error.detail} for error in errors
                        ]
                    }
                )
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class FormulaPreviewSerializer(serializers.Serializer):
    """Validates the body for `FormulaPreviewView` — an expression to
    validate/evaluate before it's ever saved as a `FormulaDefinition`."""

    expression = serializers.JSONField()
    computed_metric_type = serializers.IntegerField(required=False, allow_null=True)


class DashboardElementInputSerializer(serializers.Serializer):
    """Validates the body for `MetricTypeViewSet.dashboard_element`'s
    POST/PATCH — the write shape for a user's per-metric-type dashboard
    configuration. Removal is the separate DELETE method on the same action,
    not an implicit effect of saving with every flag off — so this always
    requires at least one `show_*` flag, same "at least one" rule as
    `MetricThresholdSerializer`'s bounds check."""

    show_chart = serializers.BooleanField(default=False)
    show_current = serializers.BooleanField(default=False)
    show_max = serializers.BooleanField(default=False)
    show_min = serializers.BooleanField(default=False)
    show_avg = serializers.BooleanField(default=False)
    timeframe = serializers.ChoiceField(
        choices=DashboardTimeframe.choices, default=DashboardTimeframe.MONTH
    )
    custom_range_start = serializers.DateField(required=False, allow_null=True, default=None)
    custom_range_end = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if not any(
            [
                attrs["show_chart"],
                attrs["show_current"],
                attrs["show_max"],
                attrs["show_min"],
                attrs["show_avg"],
            ]
        ):
            raise serializers.ValidationError(
                "Enable at least one element (chart, current, max, min, or average) — "
                "to remove this metric from the dashboard entirely, use DELETE instead."
            )
        if attrs["timeframe"] == DashboardTimeframe.CUSTOM:
            if attrs["custom_range_start"] is None or attrs["custom_range_end"] is None:
                raise serializers.ValidationError(
                    "A custom timeframe needs both custom_range_start and custom_range_end."
                )
            if attrs["custom_range_start"] > attrs["custom_range_end"]:
                raise serializers.ValidationError(
                    "custom_range_start must not be after custom_range_end."
                )
        else:
            attrs["custom_range_start"] = None
            attrs["custom_range_end"] = None
        return attrs


class DashboardElementReorderSerializer(serializers.Serializer):
    """Validates the body for the dashboard-elements reorder endpoint — an
    ordered list of metric type ids, which must exactly match the requesting
    user's current dashboard elements (checked in the view, against the DB).
    """

    metric_type_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class MetricImportSettingsSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    metric_type = serializers.PrimaryKeyRelatedField(read_only=True)
    # A separator is often meaningful whitespace (a space or a tab) — the
    # auto-generated CharField's default trim_whitespace=True would reduce
    # " " to "" and reject it as blank, so it's overridden explicitly here.
    separator = serializers.CharField(trim_whitespace=False, max_length=10)

    class Meta:
        model = MetricImportSettings
        fields = [
            "id",
            "metric_type",
            "user",
            "template",
            "separator",
            "date_format",
            "decimal_separator",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "metric_type", "user", "created_at", "updated_at"]


class BulkImportItemInputSerializer(serializers.Serializer):
    """One already client-split row: raw string tokens straight from
    positionally splitting a pasted line by the chosen template, not yet
    parsed into a typed value — see `services.resolve_bulk_import_items`."""

    value = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    date = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)


class BulkImportRequestSerializer(serializers.Serializer):
    """Validates the shared request body for both the preview and create
    bulk-import actions on `MetricTypeViewSet`."""

    items = BulkImportItemInputSerializer(many=True, allow_empty=False)
    date_format = serializers.CharField(trim_whitespace=False, min_length=1)
    decimal_separator = serializers.ChoiceField(choices=[".", ","], default=".")
    duplicate_policy = serializers.ChoiceField(choices=["skip", "overwrite"], default="skip")


class AggregateQuerySerializer(serializers.Serializer):
    """Validates the query params for `MetricTypeViewSet.aggregate`."""

    timeframe_unit = serializers.ChoiceField(choices=[unit.value for unit in TimeframeUnit])
    timeframe_count = serializers.IntegerField(min_value=1)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    relative_days = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        has_start = "start" in attrs
        has_end = "end" in attrs
        if has_start != has_end:
            raise serializers.ValidationError("start and end must be provided together.")
        if has_start and "relative_days" in attrs:
            raise serializers.ValidationError(
                "Provide either start/end or relative_days, not both."
            )
        return attrs
