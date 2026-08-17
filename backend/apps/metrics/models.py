from django.conf import settings
from django.db import models


class ValueType(models.TextChoices):
    NUMBER = "number", "Number"
    TEXT = "text", "Text"
    BOOLEAN = "boolean", "Boolean"


class Aggregation(models.TextChoices):
    SUM = "sum", "Sum"
    LAST = "last", "Last"
    AVG = "avg", "Average"


class MetricType(models.Model):
    """An admin-defined kind of thing that can be tracked (e.g. "Weight",
    "Blood glucose", "Insulin dose", "Water intake"). Deliberately generic —
    new tracked metrics are new rows here, not new models/migrations.
    """

    name = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=32, blank=True)
    value_type = models.CharField(max_length=16, choices=ValueType.choices)
    aggregation = models.CharField(max_length=16, choices=Aggregation.choices, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_metric_types",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class MetricEntry(models.Model):
    """A single logged value for a `MetricType`, owned by a user.

    `value` and `context` are JSON so this model works unmodified for any
    `MetricType` — a number reading, a boolean flag, a text note, or a
    structured dose log with metadata like injection site — without a schema
    change per metric type.
    """

    metric_type = models.ForeignKey(
        MetricType, on_delete=models.CASCADE, related_name="entries"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="metric_entries"
    )
    value = models.JSONField()
    context = models.JSONField(blank=True, null=True)
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name_plural = "metric entries"
        indexes = [
            models.Index(fields=["owner", "metric_type", "-recorded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.metric_type.name} @ {self.recorded_at:%Y-%m-%d %H:%M} ({self.owner})"
