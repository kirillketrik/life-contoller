from django.conf import settings
from django.db import models


class ValueType(models.TextChoices):
    NUMBER = "number", "Number"
    TEXT = "text", "Text"
    BOOLEAN = "boolean", "Boolean"
    DATE = "date", "Date"
    CHOICE = "choice", "Choice"


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
    through `MetricEntry` — see `apps.metrics.formula_engine`.

    `is_singleton` marks a metric type that holds one fact about the user
    rather than a time series (e.g. Sex, Date of birth) — a user should edit
    their one `MetricEntry` for it, not accumulate new ones. Enforced in
    `MetricEntrySerializer.validate` on create; the frontend hides the "add
    entry" affordance in favor of "edit" once an entry exists.
    """

    name = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=32, blank=True)
    value_type = models.CharField(max_length=16, choices=ValueType.choices)
    aggregation = models.CharField(max_length=16, choices=Aggregation.choices, blank=True)
    is_computed = models.BooleanField(default=False)
    is_singleton = models.BooleanField(default=False)
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


class MetricTypeChoice(models.Model):
    """One fixed option of a `choice`-valued `MetricType` (e.g. Sex: male/female).

    `code` is the stable identifier a `MetricEntry.value` stores and formulas
    compare against — never shown to the user. `label` is the Russian text
    shown in the UI. `numeric_value` is optional: set it when the option
    should feed a calculation as a number (e.g. Activity Level's TDEE
    multiplier); leave it null when the option is only ever compared by code
    (e.g. Sex, used in an `if/then/else` formula branch, never arithmetic).
    """

    metric_type = models.ForeignKey(MetricType, on_delete=models.CASCADE, related_name="choices")
    code = models.CharField(max_length=64)
    label = models.CharField(max_length=100)
    numeric_value = models.FloatField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["metric_type", "code"], name="unique_choice_code_per_metric_type"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.metric_type.name}: {self.label} ({self.code})"


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


class FavoriteMetric(models.Model):
    """A user's favorited metric type, shown on their personal dashboard.

    Per-user, not global — favoriting is a personal preference, scoped like
    `MetricThreshold`, not a shared/admin-defined resource like `MetricType`
    itself. `order` supports user-controlled ordering of the dashboard's
    favorites section (defaults to 0 for every new favorite, so insertion
    order — via `created_at` — is the tie-breaker until explicitly reordered).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_metrics"
    )
    metric_type = models.ForeignKey(
        MetricType, on_delete=models.CASCADE, related_name="favorited_by"
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "metric_type"], name="unique_favorite_metric_per_user"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.metric_type.name} favorited by {self.user}"


class FormulaDefinition(models.Model):
    """Defines how a computed `MetricType` (`is_computed=True`) is derived
    from other metric types. There is exactly one definition per computed
    metric type; the definition itself is global (admin-defined), while the
    inputs it references are resolved per-user at evaluation time.

    `expression` is an AST (see `apps.metrics.formula_engine.nodes`) stored as
    JSON — operator/function/comparison/conditional nodes with metric-type or
    constant leaves. Deliberately not a string expression evaluated via
    `eval`: the builder UI composes this tree visually, and it's parsed by a
    strict recursive validator before ever being evaluated.
    """

    computed_metric_type = models.OneToOneField(
        MetricType, on_delete=models.CASCADE, related_name="formula_definition"
    )
    expression = models.JSONField(help_text="The formula's AST — see apps.metrics.formula_engine.")
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
        return f"{self.computed_metric_type.name} formula"
