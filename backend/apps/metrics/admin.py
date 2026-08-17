from django.contrib import admin

from .models import MetricEntry, MetricType


@admin.register(MetricType)
class MetricTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "unit", "value_type", "aggregation", "created_by", "created_at"]
    list_filter = ["value_type", "aggregation"]
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
