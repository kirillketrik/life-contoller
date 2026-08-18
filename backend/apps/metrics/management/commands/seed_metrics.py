"""Seeds the baseline MetricTypes and FormulaDefinitions the built-in formulas
(bmi, body_fat_navy, tdee_mifflin — see apps.metrics.formulas) need to
actually produce values, plus the computed MetricTypes themselves.

Idempotent: re-running only fills in whatever is still missing, matched by
MetricType.name. Safe to run repeatedly (e.g. on every `docker compose up`).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.metrics.models import Aggregation, FormulaDefinition, MetricType, ValueType

User = get_user_model()

# key -> (name, unit, value_type, aggregation)
# "sex" and "activity_level" are free-text inputs (no dropdown in the entry
# dialog today), but apps.metrics.formulas hardcodes the English values it
# expects (male/female; sedentary/light/moderate/active/very_active) — so the
# accepted values are spelled out in the name itself to guide data entry.
INPUT_METRIC_TYPES: dict[str, tuple[str, str, str, str]] = {
    "weight_kg": ("Вес", "kg", ValueType.NUMBER, Aggregation.LAST),
    "height_cm": ("Рост", "cm", ValueType.NUMBER, Aggregation.LAST),
    "dob": ("Дата рождения", "", ValueType.DATE, ""),
    "sex": ("Пол (male / female)", "", ValueType.TEXT, ""),
    "activity_level": (
        "Уровень активности (sedentary/light/moderate/active/very_active)",
        "",
        ValueType.TEXT,
        "",
    ),
    "neck_cm": ("Обхват шеи", "cm", ValueType.NUMBER, Aggregation.LAST),
    "waist_cm": ("Обхват талии", "cm", ValueType.NUMBER, Aggregation.LAST),
    "hip_cm": ("Обхват бёдер", "cm", ValueType.NUMBER, Aggregation.LAST),
}

# formula_key -> (computed metric type name, unit, {formula var -> input key})
COMPUTED_METRIC_TYPES: dict[str, tuple[str, str, dict[str, str]]] = {
    FormulaDefinition.FormulaKey.BMI: (
        "ИМТ",
        "kg/m²",
        {"weight_kg": "weight_kg", "height_cm": "height_cm"},
    ),
    FormulaDefinition.FormulaKey.BODY_FAT_NAVY: (
        "Процент жира (метод ВМФ США)",
        "%",
        {
            "waist_cm": "waist_cm",
            "neck_cm": "neck_cm",
            "height_cm": "height_cm",
            "sex": "sex",
            "hip_cm": "hip_cm",
        },
    ),
    FormulaDefinition.FormulaKey.TDEE_MIFFLIN: (
        "TDEE (Миффлин-Сан Жеор)",
        "kcal",
        {
            "weight_kg": "weight_kg",
            "height_cm": "height_cm",
            "dob": "dob",
            "sex": "sex",
            "activity_level": "activity_level",
        },
    ),
}


class Command(BaseCommand):
    help = "Seeds baseline MetricTypes and FormulaDefinitions for BMI/body-fat/TDEE."

    @transaction.atomic
    def handle(self, *args, **options):
        creator = User.objects.filter(is_superuser=True).order_by("id").first()

        input_types: dict[str, MetricType] = {}
        for key, (name, unit, value_type, aggregation) in INPUT_METRIC_TYPES.items():
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

        for formula_key, (name, unit, var_to_key) in COMPUTED_METRIC_TYPES.items():
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

            input_mapping = {var: input_types[key].id for var, key in var_to_key.items()}
            _, formula_created = FormulaDefinition.objects.get_or_create(
                computed_metric_type=computed_type,
                defaults={
                    "formula_key": formula_key,
                    "input_mapping": input_mapping,
                    "created_by": creator,
                },
            )
            self._report(f"{name} formula ({formula_key})", formula_created)

    def _report(self, label: str, created: bool) -> None:
        status = "created" if created else "already exists"
        self.stdout.write(f"  {label}: {status}")
