from django.contrib import admin

from .models import (
    DashboardElement,
    FormulaDefinition,
    MetricEntry,
    MetricImportSettings,
    MetricThreshold,
    MetricType,
    MetricTypeChoice,
)


class MetricTypeChoiceInline(admin.TabularInline):
    model = MetricTypeChoice
    extra = 0


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
    inlines = [MetricTypeChoiceInline]

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


@admin.register(DashboardElement)
class DashboardElementAdmin(admin.ModelAdmin):
    list_display = [
        "metric_type",
        "user",
        "show_chart",
        "show_current",
        "show_max",
        "show_min",
        "show_avg",
        "timeframe",
        "order",
        "created_at",
    ]
    list_filter = ["metric_type", "timeframe"]
    search_fields = ["user__username", "metric_type__name"]
    autocomplete_fields = ["metric_type", "user"]


@admin.register(MetricImportSettings)
class MetricImportSettingsAdmin(admin.ModelAdmin):
    list_display = ["metric_type", "user", "template", "separator", "date_format"]
    list_filter = ["metric_type"]
    search_fields = ["user__username", "metric_type__name"]
    autocomplete_fields = ["metric_type", "user"]


@admin.register(FormulaDefinition)
class FormulaDefinitionAdmin(admin.ModelAdmin):
    list_display = ["computed_metric_type", "created_by", "created_at"]
    search_fields = ["computed_metric_type__name"]
    autocomplete_fields = ["computed_metric_type"]

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
