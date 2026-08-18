# Adds MetricType.is_singleton and marks the existing "one fact, not a
# series" metric types (Sex, Date of birth) as singleton on already-seeded
# databases — seed_metrics.py's get_or_create defaults only apply on first
# creation, so pre-existing rows need this data backfill too.

from django.db import migrations, models

SINGLETON_METRIC_TYPE_NAMES = ["Пол", "Дата рождения"]


def mark_existing_singletons(apps, schema_editor):
    MetricType = apps.get_model("metrics", "MetricType")
    MetricType.objects.filter(name__in=SINGLETON_METRIC_TYPE_NAMES).update(is_singleton=True)


def unmark_existing_singletons(apps, schema_editor):
    MetricType = apps.get_model("metrics", "MetricType")
    MetricType.objects.filter(name__in=SINGLETON_METRIC_TYPE_NAMES).update(is_singleton=False)


class Migration(migrations.Migration):

    dependencies = [
        ("metrics", "0008_finalize_formula_expression"),
    ]

    operations = [
        migrations.AddField(
            model_name="metrictype",
            name="is_singleton",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_singletons, unmark_existing_singletons),
    ]
