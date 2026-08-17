from rest_framework import serializers

from .models import MetricEntry, MetricType


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
        if metric_type is not None and value is not None:
            self._validate_value_matches_type(metric_type, value)
        return attrs

    @staticmethod
    def _validate_value_matches_type(metric_type, value) -> None:
        from .models import ValueType

        expectations = {
            ValueType.NUMBER: (int, float),
            ValueType.BOOLEAN: bool,
            ValueType.TEXT: str,
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
