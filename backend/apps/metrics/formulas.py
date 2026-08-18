"""Evaluation engine for computed metric types (`FormulaDefinition`).

A computed metric type has no `MetricEntry` rows of its own. Instead, its
value at any timestamp T is derived from the most recent (as-of T) value of
each of its input metric types, per user — see `evaluate_formula`. Running
that across the timestamps its inputs actually changed at (`computed_series`)
produces a `DataPoint` list, which is exactly what `apps.metrics.aggregation`
consumes for regular metric types too — so computed metrics are chartable
over time through the same pipeline, not just readable as a single current
value.

Adding a new formula: add its required variable names to `FORMULA_INPUT_VARS`
and a compute function to `_FORMULA_COMPUTE`, keyed by the same
`FormulaDefinition.FormulaKey` value.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime

from .aggregation import DataPoint
from .models import FormulaDefinition, MetricEntry

_ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

# Formula variable name -> input MetricType it's read from (via input_mapping).
# "dob" is special-cased in evaluate_formula: it's resolved to "age" (years,
# as of the evaluation timestamp) before the compute function ever sees it.
FORMULA_INPUT_VARS: dict[str, tuple[str, ...]] = {
    "bmi": ("weight_kg", "height_cm"),
    "body_fat_navy": ("waist_cm", "neck_cm", "height_cm", "sex", "hip_cm"),
    "tdee_mifflin": ("weight_kg", "height_cm", "dob", "sex", "activity_level"),
}


def as_of_value(*, metric_type_id: int, user, at: datetime):
    """The most recently recorded value of `metric_type_id` for `user` at or
    before `at`, or None if the user has no such entry yet."""
    entry = (
        MetricEntry.objects.filter(metric_type_id=metric_type_id, owner=user, recorded_at__lte=at)
        .order_by("-recorded_at")
        .first()
    )
    return entry.value if entry else None


def _age_years(dob_value, at: datetime) -> int | None:
    try:
        dob = date.fromisoformat(str(dob_value))
    except ValueError:
        return None
    reference = at.date()
    age = reference.year - dob.year - ((reference.month, reference.day) < (dob.month, dob.day))
    return age if age >= 0 else None


def _bmi(values: dict) -> float | None:
    weight_kg = values.get("weight_kg")
    height_cm = values.get("height_cm")
    if weight_kg is None or not height_cm:
        return None
    height_m = height_cm / 100
    return weight_kg / (height_m**2)


def _body_fat_navy(values: dict) -> float | None:
    waist_cm = values.get("waist_cm")
    neck_cm = values.get("neck_cm")
    height_cm = values.get("height_cm")
    sex = values.get("sex")
    if waist_cm is None or neck_cm is None or height_cm is None or sex is None:
        return None
    sex = str(sex).strip().lower()
    if sex == "male":
        diff = waist_cm - neck_cm
        if diff <= 0:
            return None
        return 495 / (1.0324 - 0.19077 * math.log10(diff) + 0.15456 * math.log10(height_cm)) - 450
    if sex == "female":
        hip_cm = values.get("hip_cm")
        if hip_cm is None:
            return None
        diff = waist_cm + hip_cm - neck_cm
        if diff <= 0:
            return None
        return (
            495 / (1.29579 - 0.35004 * math.log10(diff) + 0.22100 * math.log10(height_cm)) - 450
        )
    return None


def _tdee_mifflin(values: dict) -> float | None:
    weight_kg = values.get("weight_kg")
    height_cm = values.get("height_cm")
    age = values.get("age")
    sex = values.get("sex")
    activity_level = values.get("activity_level")
    if None in (weight_kg, height_cm, age, sex, activity_level):
        return None
    sex = str(sex).strip().lower()
    if sex == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    elif sex == "female":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        return None
    multiplier = _ACTIVITY_MULTIPLIERS.get(str(activity_level).strip().lower())
    if multiplier is None:
        return None
    return bmr * multiplier


_FORMULA_COMPUTE: dict[str, Callable[[dict], float | None]] = {
    "bmi": _bmi,
    "body_fat_navy": _body_fat_navy,
    "tdee_mifflin": _tdee_mifflin,
}


def evaluate_formula(formula_definition: FormulaDefinition, *, user, at: datetime) -> float | None:
    """The formula's value for `user` as-of `at`. Returns None (never a
    default/fake value) if any input required for this user/branch of the
    formula (e.g. hip circumference only matters for the female Navy
    body-fat branch) has no recorded value yet as of `at`.
    """
    input_vars = FORMULA_INPUT_VARS[formula_definition.formula_key]
    values: dict[str, object] = {}
    for var in input_vars:
        metric_type_id = formula_definition.input_mapping.get(var)
        if metric_type_id is None:
            continue
        value = as_of_value(metric_type_id=metric_type_id, user=user, at=at)
        if value is not None:
            values[var] = value

    if "dob" in values:
        age = _age_years(values.pop("dob"), at)
        if age is not None:
            values["age"] = age

    compute = _FORMULA_COMPUTE[formula_definition.formula_key]
    return compute(values)


def computed_series(
    formula_definition: FormulaDefinition, *, user, range_start: datetime, range_end: datetime
) -> list[DataPoint]:
    """Evaluate the formula at every timestamp any of its inputs has an
    entry at within [range_start, range_end], for `user`. Timestamps where
    a required input is still missing are simply omitted from the result.
    """
    input_metric_type_ids = [
        metric_type_id
        for metric_type_id in formula_definition.input_mapping.values()
        if metric_type_id is not None
    ]
    timestamps = set(
        MetricEntry.objects.filter(
            metric_type_id__in=input_metric_type_ids,
            owner=user,
            recorded_at__gte=range_start,
            recorded_at__lte=range_end,
        ).values_list("recorded_at", flat=True)
    )

    points = []
    for timestamp in sorted(timestamps):
        value = evaluate_formula(formula_definition, user=user, at=timestamp)
        if value is not None:
            points.append(DataPoint(recorded_at=timestamp, value=value))
    return points
