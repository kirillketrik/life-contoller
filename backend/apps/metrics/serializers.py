from datetime import date

from rest_framework import serializers

from .aggregation import TimeframeUnit
from .formulas import FORMULA_INPUT_VARS
from .models import FormulaDefinition, MetricEntry, MetricThreshold, MetricType, ValueType


class MetricTypeSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = MetricType
        fields = [
            "id",
            "name",
            "unit",
            "value_type",
            "aggregation",
            "is_computed",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


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
            "formula_key",
            "input_mapping",
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

        formula_key = attrs.get("formula_key") or getattr(self.instance, "formula_key", None)
        input_mapping = attrs.get("input_mapping", getattr(self.instance, "input_mapping", None))
        if formula_key and input_mapping is not None:
            if not isinstance(input_mapping, dict):
                raise serializers.ValidationError(
                    {
                        "input_mapping": (
                            "Must be an object mapping variable name to input MetricType id."
                        )
                    }
                )
            allowed_vars = set(FORMULA_INPUT_VARS.get(formula_key, ()))
            unknown = set(input_mapping) - allowed_vars
            if unknown:
                raise serializers.ValidationError(
                    {"input_mapping": f"Unknown variables for '{formula_key}': {sorted(unknown)}."}
                )
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


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
