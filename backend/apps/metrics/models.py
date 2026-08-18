from django.conf import settings
from django.db import models


class ValueType(models.TextChoices):
    NUMBER = "number", "Number"
    TEXT = "text", "Text"
    BOOLEAN = "boolean", "Boolean"
    DATE = "date", "Date"


class Aggregation(models.TextChoices):
    SUM = "sum", "Sum"
    LAST = "last", "Last"
    AVG = "avg", "Average"


class MetricType(models.Model):
    """An admin-defined kind of thing that can be tracked (e.g. "Weight",
    "Blood glucose", "Insulin dose", "Water intake"). Deliberately generic —
    new tracked metrics are new rows here, not new models/migrations.

    `is_computed` marks a virtual metric type whose values are derived from
    other metric types via a `FormulaDefinition` rather than logged directly
    through `MetricEntry` — see `apps.metrics.formulas`.
    """

    name = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=32, blank=True)
    value_type = models.CharField(max_length=16, choices=ValueType.choices)
    aggregation = models.CharField(max_length=16, choices=Aggregation.choices, blank=True)
    is_computed = models.BooleanField(default=False)
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


class MetricThreshold(models.Model):
    """A per-user, per-metric-type "healthy range" used for the % time-in-range
    stat. Either bound may be null independently (e.g. an upper-bound-only
    threshold for a metric where only "too high" matters).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="metric_thresholds"
    )
    metric_type = models.ForeignKey(MetricType, on_delete=models.CASCADE, related_name="thresholds")
    lower_bound = models.FloatField(null=True, blank=True)
    upper_bound = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["metric_type__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "metric_type"], name="unique_threshold_per_user_metric_type"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.metric_type.name} threshold for {self.user}"


class FormulaDefinition(models.Model):
    """Defines how a computed `MetricType` (`is_computed=True`) is derived
    from other metric types. There is exactly one definition per computed
    metric type; the definition itself is global (admin-defined), while the
    inputs it references are resolved per-user at evaluation time — see
    `apps.metrics.formulas`.
    """

    class FormulaKey(models.TextChoices):
        BMI = "bmi", "BMI"
        BODY_FAT_NAVY = "body_fat_navy", "Body fat % (Navy method)"
        TDEE_MIFFLIN = "tdee_mifflin", "TDEE (Mifflin-St Jeor)"

    computed_metric_type = models.OneToOneField(
        MetricType, on_delete=models.CASCADE, related_name="formula_definition"
    )
    formula_key = models.CharField(max_length=32, choices=FormulaKey.choices)
    input_mapping = models.JSONField(
        help_text="Maps formula variable name (e.g. 'weight_kg') to the input MetricType id "
        "it should be read from for the current user."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_formula_definitions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["computed_metric_type__name"]

    def __str__(self) -> str:
        return f"{self.computed_metric_type.name} = {self.formula_key}"
