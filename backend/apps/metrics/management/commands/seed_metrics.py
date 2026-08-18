"""Seeds the baseline MetricTypes (incl. the Sex / Activity Level choice
metrics) and the three built-in FormulaDefinitions (BMI, body-fat % Navy
method, TDEE Mifflin-St Jeor) on top of apps.metrics.formula_engine.

Idempotent: re-running only fills in whatever is still missing, matched by
MetricType.name. Safe to run repeatedly (e.g. on every `docker compose up`).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.metrics.formula_engine import builtins
from apps.metrics.models import (
    Aggregation,
    FormulaDefinition,
    MetricType,
    MetricTypeChoice,
    ValueType,
)

User = get_user_model()

# key -> (name, unit, value_type, aggregation)
NUMBER_METRIC_TYPES: dict[str, tuple[str, str, str, str]] = {
    "weight_kg": ("Вес", "kg", ValueType.NUMBER, Aggregation.LAST),
    "height_cm": ("Рост", "cm", ValueType.NUMBER, Aggregation.LAST),
    "neck_cm": ("Обхват шеи", "cm", ValueType.NUMBER, Aggregation.LAST),
    "waist_cm": ("Обхват талии", "cm", ValueType.NUMBER, Aggregation.LAST),
    "hip_cm": ("Обхват бёдер", "cm", ValueType.NUMBER, Aggregation.LAST),
}

DATE_METRIC_TYPES: dict[str, str] = {
    "dob": "Дата рождения",
}

# key -> (name, [(code, label, numeric_value | None), ...])
CHOICE_METRIC_TYPES: dict[str, tuple[str, list[tuple[str, str, float | None]]]] = {
    "sex": (
        "Пол",
        [
            ("male", "Мужской", None),
            ("female", "Женский", None),
        ],
    ),
    "activity_level": (
        "Уровень активности",
        [
            ("sedentary", "Сидячий образ жизни", 1.2),
            ("light", "Лёгкая активность", 1.375),
            ("moderate", "Умеренная активность", 1.55),
            ("active", "Высокая активность", 1.725),
            ("very_active", "Очень высокая активность", 1.9),
        ],
    ),
}

# formula name -> (computed metric type name, unit, builder function name)
COMPUTED_METRIC_TYPES = {
    "bmi": ("ИМТ", "kg/m²"),
    "body_fat_navy": ("Процент жира (метод ВМФ США)", "%"),
    "tdee_mifflin": ("TDEE (Миффлин-Сан Жеор)", "ккал"),
}


class Command(BaseCommand):
    help = "Seeds baseline MetricTypes and FormulaDefinitions for BMI/body-fat/TDEE."

    @transaction.atomic
    def handle(self, *args, **options):
        creator = User.objects.filter(is_superuser=True).order_by("id").first()

        input_types: dict[str, MetricType] = {}

        for key, (name, unit, value_type, aggregation) in NUMBER_METRIC_TYPES.items():
            metric_type, created = MetricType.objects.get_or_create(
                name=name,
                defaults={
                    "unit": unit,
                    "value_type": value_type,
                    "aggregation": aggregation,
                    "created_by": creator,
                },
            )
            input_types[key] = metric_type
            self._report(name, created)

        for key, name in DATE_METRIC_TYPES.items():
            metric_type, created = MetricType.objects.get_or_create(
                name=name, defaults={"value_type": ValueType.DATE, "created_by": creator}
            )
            input_types[key] = metric_type
            self._report(name, created)

        for key, (name, options) in CHOICE_METRIC_TYPES.items():
            metric_type, created = MetricType.objects.get_or_create(
                name=name, defaults={"value_type": ValueType.CHOICE, "created_by": creator}
            )
            input_types[key] = metric_type
            self._report(name, created)
            for order, (code, label, numeric_value) in enumerate(options):
                _, option_created = MetricTypeChoice.objects.get_or_create(
                    metric_type=metric_type,
                    code=code,
                    defaults={"label": label, "numeric_value": numeric_value, "order": order},
                )
                self._report(f"  {name} option '{code}'", option_created)

        builders = {
            "bmi": lambda: builtins.build_bmi(
                weight_kg_id=input_types["weight_kg"].id, height_cm_id=input_types["height_cm"].id
            ),
            "body_fat_navy": lambda: builtins.build_body_fat_navy(
                waist_cm_id=input_types["waist_cm"].id,
                neck_cm_id=input_types["neck_cm"].id,
                height_cm_id=input_types["height_cm"].id,
                hip_cm_id=input_types["hip_cm"].id,
                sex_id=input_types["sex"].id,
            ),
            "tdee_mifflin": lambda: builtins.build_tdee_mifflin(
                weight_kg_id=input_types["weight_kg"].id,
                height_cm_id=input_types["height_cm"].id,
                dob_id=input_types["dob"].id,
                sex_id=input_types["sex"].id,
                activity_level_id=input_types["activity_level"].id,
            ),
        }

        for formula_name, (name, unit) in COMPUTED_METRIC_TYPES.items():
            computed_type, created = MetricType.objects.get_or_create(
                name=name,
                defaults={
                    "unit": unit,
                    "value_type": ValueType.NUMBER,
                    "is_computed": True,
                    "created_by": creator,
                },
            )
            self._report(name, created)

            _, formula_created = FormulaDefinition.objects.get_or_create(
                computed_metric_type=computed_type,
                defaults={"expression": builders[formula_name](), "created_by": creator},
            )
            self._report(f"{name} formula ({formula_name})", formula_created)

    def _report(self, label: str, created: bool) -> None:
        status = "created" if created else "already exists"
        self.stdout.write(f"  {label}: {status}")
