from django.contrib import admin

from .models import FormulaDefinition, MetricEntry, MetricThreshold, MetricType


@admin.register(MetricType)
class MetricTypeAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "unit",
        "value_type",
        "aggregation",
        "is_computed",
        "created_by",
        "created_at",
    ]
    list_filter = ["value_type", "aggregation", "is_computed"]
    search_fields = ["name"]

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MetricEntry)
class MetricEntryAdmin(admin.ModelAdmin):
    list_display = ["metric_type", "owner", "value", "recorded_at"]
    list_filter = ["metric_type"]
    search_fields = ["owner__username", "metric_type__name"]
    autocomplete_fields = ["metric_type", "owner"]
    date_hierarchy = "recorded_at"


@admin.register(MetricThreshold)
class MetricThresholdAdmin(admin.ModelAdmin):
    list_display = ["metric_type", "user", "lower_bound", "upper_bound"]
    list_filter = ["metric_type"]
    search_fields = ["user__username", "metric_type__name"]
    autocomplete_fields = ["metric_type", "user"]


@admin.register(FormulaDefinition)
class FormulaDefinitionAdmin(admin.ModelAdmin):
    list_display = ["computed_metric_type", "formula_key", "created_by", "created_at"]
    list_filter = ["formula_key"]
    search_fields = ["computed_metric_type__name"]
    autocomplete_fields = ["computed_metric_type"]

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
