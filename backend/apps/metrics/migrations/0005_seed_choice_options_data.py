# Data migration: converts the free-text Sex / Activity Level MetricTypes to
# the new `choice` value type with their fixed option lists, best-effort
# remaps existing MetricEntry text values to the new option codes, and
# localizes the TDEE MetricType's unit (kcal -> ккал).

from django.db import migrations

SEX_OPTIONS = [
    ("male", "Мужской"),
    ("female", "Женский"),
]

ACTIVITY_LEVEL_OPTIONS = [
    ("sedentary", "Сидячий образ жизни", 1.2),
    ("light", "Лёгкая активность", 1.375),
    ("moderate", "Умеренная активность", 1.55),
    ("active", "Высокая активность", 1.725),
    ("very_active", "Очень высокая активность", 1.9),
]

OLD_SEX_NAME = "Пол (male / female)"
NEW_SEX_NAME = "Пол"
OLD_ACTIVITY_NAME = "Уровень активности (sedentary/light/moderate/active/very_active)"
NEW_ACTIVITY_NAME = "Уровень активности"
OLD_TDEE_UNIT = "kcal"
NEW_TDEE_UNIT = "ккал"
TDEE_NAME = "TDEE (Миффлин-Сан Жеор)"


def _convert_to_choice(
    apps, metric_type, *, new_name: str, options: list[tuple], code_index: int, label_index: int
):
    MetricTypeChoice = apps.get_model("metrics", "MetricTypeChoice")
    MetricEntry = apps.get_model("metrics", "MetricEntry")

    codes_by_lowercase: dict[str, str] = {}
    for order, option in enumerate(options):
        code, label = option[code_index], option[label_index]
        numeric_value = option[2] if len(option) > 2 else None
        MetricTypeChoice.objects.create(
            metric_type=metric_type,
            code=code,
            label=label,
            numeric_value=numeric_value,
            order=order,
        )
        codes_by_lowercase[code.lower()] = code
        codes_by_lowercase[label.lower()] = code

    for entry in MetricEntry.objects.filter(metric_type=metric_type):
        raw = str(entry.value).strip().lower() if entry.value is not None else ""
        matched_code = codes_by_lowercase.get(raw)
        if matched_code is not None and matched_code != entry.value:
            entry.value = matched_code
            entry.save(update_fields=["value"])

    metric_type.name = new_name
    metric_type.value_type = "choice"
    metric_type.save(update_fields=["name", "value_type"])


def convert_forward(apps, schema_editor):
    MetricType = apps.get_model("metrics", "MetricType")

    sex_type = MetricType.objects.filter(name=OLD_SEX_NAME).first()
    if sex_type is not None:
        _convert_to_choice(
            apps, sex_type, new_name=NEW_SEX_NAME, options=SEX_OPTIONS, code_index=0, label_index=1
        )

    activity_type = MetricType.objects.filter(name=OLD_ACTIVITY_NAME).first()
    if activity_type is not None:
        _convert_to_choice(
            apps,
            activity_type,
            new_name=NEW_ACTIVITY_NAME,
            options=ACTIVITY_LEVEL_OPTIONS,
            code_index=0,
            label_index=1,
        )

    MetricType.objects.filter(name=TDEE_NAME, unit=OLD_TDEE_UNIT).update(unit=NEW_TDEE_UNIT)


def convert_backward(apps, schema_editor):
    MetricType = apps.get_model("metrics", "MetricType")
    MetricTypeChoice = apps.get_model("metrics", "MetricTypeChoice")

    sex_type = MetricType.objects.filter(name=NEW_SEX_NAME).first()
    if sex_type is not None:
        MetricTypeChoice.objects.filter(metric_type=sex_type).delete()
        sex_type.name = OLD_SEX_NAME
        sex_type.value_type = "text"
        sex_type.save(update_fields=["name", "value_type"])

    activity_type = MetricType.objects.filter(name=NEW_ACTIVITY_NAME).first()
    if activity_type is not None:
        MetricTypeChoice.objects.filter(metric_type=activity_type).delete()
        activity_type.name = OLD_ACTIVITY_NAME
        activity_type.value_type = "text"
        activity_type.save(update_fields=["name", "value_type"])

    MetricType.objects.filter(name=TDEE_NAME, unit=NEW_TDEE_UNIT).update(unit=OLD_TDEE_UNIT)


class Migration(migrations.Migration):

    dependencies = [
        ("metrics", "0004_choice_metrics"),
    ]

    operations = [
        migrations.RunPython(convert_forward, convert_backward),
    ]
