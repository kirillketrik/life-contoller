"""Seeds the baseline NutrientType catalog (common vitamins/minerals plus the
usual macro-breakdown nutrients — fiber, sugar, saturated fat, etc.) as
`is_system=True` rows.

Idempotent: re-running only fills in whatever is still missing, matched by
NutrientType.name. Safe to run repeatedly (e.g. on every `docker compose up`),
same convention as `apps.metrics.management.commands.seed_metrics`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.nutrition.models import NutrientCategory, NutrientType

# name -> (unit, category). Sub-macro breakdown nutrients (fiber, sugar,
# saturated fat, cholesterol, sodium) are categorized MACRO — they're still
# part of the macronutrient picture, just not one of the four fixed FoodItem
# columns; vitamins/minerals are MICRO.
NUTRIENT_TYPES: dict[str, tuple[str, str]] = {
    "Клетчатка": ("g", NutrientCategory.MACRO),
    "Сахар": ("g", NutrientCategory.MACRO),
    "Насыщенные жиры": ("g", NutrientCategory.MACRO),
    "Трансжиры": ("g", NutrientCategory.MACRO),
    "Холестерин": ("mg", NutrientCategory.MACRO),
    "Натрий": ("mg", NutrientCategory.MACRO),
    "Витамин A": ("mcg", NutrientCategory.MICRO),
    "Витамин C": ("mg", NutrientCategory.MICRO),
    "Витамин D": ("mcg", NutrientCategory.MICRO),
    "Витамин E": ("mg", NutrientCategory.MICRO),
    "Витамин K": ("mcg", NutrientCategory.MICRO),
    "Витамин B12": ("mcg", NutrientCategory.MICRO),
    "Фолиевая кислота": ("mcg", NutrientCategory.MICRO),
    "Кальций": ("mg", NutrientCategory.MICRO),
    "Железо": ("mg", NutrientCategory.MICRO),
    "Магний": ("mg", NutrientCategory.MICRO),
    "Калий": ("mg", NutrientCategory.MICRO),
    "Цинк": ("mg", NutrientCategory.MICRO),
}


class Command(BaseCommand):
    help = "Seeds the baseline NutrientType catalog (vitamins, minerals, macro breakdown)."

    @transaction.atomic
    def handle(self, *args, **options):
        for name, (unit, category) in NUTRIENT_TYPES.items():
            _, created = NutrientType.objects.get_or_create(
                name=name,
                defaults={"unit": unit, "category": category, "is_system": True},
            )
            self._report(name, created)

    def _report(self, label: str, created: bool) -> None:
        status = "created" if created else "already exists"
        self.stdout.write(f"  {label}: {status}")
