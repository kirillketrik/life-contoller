"""Seeds the four materialized daily nutrition-total MetricTypes (Калории/
Белки/Жиры/Углеводы (день) — see apps.nutrition.services.recompute_daily_
nutrition_metrics, which is what actually populates their MetricEntry rows)
and, if the TDEE metric type has already been seeded (via apps.metrics's
seed_metrics), a computed "% дневной нормы калорий" MetricType/FormulaDefinition
comparing daily calories eaten against it — reusing the existing AST formula
engine exactly as-is (a plain division + multiplication), per CLAUDE.md's
"Integration with metrics" design decision.

Idempotent, matches on MetricType.name — safe to re-run. Run seed_metrics
first if you want the "% of daily target" formula seeded in the same pass;
otherwise re-run this command later once seed_metrics has been run.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.metrics.formula_engine.builtins import binop, const, metric
from apps.metrics.models import Aggregation, FormulaDefinition, MetricType, ValueType
from apps.nutrition.services import DAILY_METRIC_NAMES

User = get_user_model()

DAILY_METRIC_UNITS: dict[str, str] = {
    "calories": "ккал",
    "protein": "г",
    "fat": "г",
    "carbs": "г",
}

TDEE_METRIC_NAME = "TDEE (Миффлин-Сан Жеор)"
CALORIE_TARGET_METRIC_NAME = "% дневной нормы калорий"


class Command(BaseCommand):
    help = (
        "Seeds the daily nutrition-total MetricTypes and, if TDEE is already "
        "seeded, the %% of daily caloric target formula."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        creator = User.objects.filter(is_superuser=True).order_by("id").first()

        daily_types: dict[str, MetricType] = {}
        for key, name in DAILY_METRIC_NAMES.items():
            metric_type, created = MetricType.objects.get_or_create(
                name=name,
                defaults={
                    "unit": DAILY_METRIC_UNITS[key],
                    "value_type": ValueType.NUMBER,
                    "aggregation": Aggregation.SUM,
                    "created_by": creator,
                },
            )
            daily_types[key] = metric_type
            self._report(name, created)

        tdee_type = MetricType.objects.filter(name=TDEE_METRIC_NAME).first()
        if tdee_type is None:
            self.stdout.write(
                f"  Skipping '{CALORIE_TARGET_METRIC_NAME}': '{TDEE_METRIC_NAME}' not seeded yet "
                "(run seed_metrics first, then re-run this command)."
            )
            return

        target_type, created = MetricType.objects.get_or_create(
            name=CALORIE_TARGET_METRIC_NAME,
            defaults={
                "unit": "%",
                "value_type": ValueType.NUMBER,
                "is_computed": True,
                "created_by": creator,
            },
        )
        self._report(CALORIE_TARGET_METRIC_NAME, created)

        expression = binop(
            "*", binop("/", metric(daily_types["calories"].id), metric(tdee_type.id)), const(100)
        )
        _, formula_created = FormulaDefinition.objects.get_or_create(
            computed_metric_type=target_type,
            defaults={"expression": expression, "created_by": creator},
        )
        self._report(f"{CALORIE_TARGET_METRIC_NAME} formula", formula_created)

    def _report(self, label: str, created: bool) -> None:
        status = "created" if created else "already exists"
        self.stdout.write(f"  {label}: {status}")
