"""Write-side logic that doesn't fit in a serializer's create/update — see
CLAUDE.md's backend-layering convention. First (and so far only) use: creating
or replacing a `MetricType`'s `MetricTypeChoice` rows is a multi-model write
that should commit atomically with the `MetricType` itself.
"""

from __future__ import annotations

from django.db import transaction

from .models import MetricType, MetricTypeChoice


def create_metric_type_with_choices(
    *, validated_data: dict, choices_data: list[dict], user
) -> MetricType:
    with transaction.atomic():
        metric_type = MetricType.objects.create(created_by=user, **validated_data)
        _replace_choices(metric_type, choices_data)
    return metric_type


def update_metric_type_choices(*, metric_type: MetricType, choices_data: list[dict]) -> None:
    with transaction.atomic():
        _replace_choices(metric_type, choices_data)


def _replace_choices(metric_type: MetricType, choices_data: list[dict]) -> None:
    metric_type.choices.all().delete()
    MetricTypeChoice.objects.bulk_create(
        [
            MetricTypeChoice(
                metric_type=metric_type,
                code=choice["code"],
                label=choice["label"],
                numeric_value=choice.get("numeric_value"),
                order=choice.get("order", index),
            )
            for index, choice in enumerate(choices_data)
        ]
    )
