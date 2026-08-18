"""Builds the raw expression dicts for the three built-in formulas (BMI,
body-fat % Navy method, TDEE Mifflin-St Jeor) — used by `seed_metrics` and the
`0007` data migration that converts pre-engine `FormulaDefinition` rows. Pure
functions of metric type ids; no DB access here.
"""

from __future__ import annotations


def metric(metric_type_id: int) -> dict:
    return {"type": "metric", "metric_type_id": metric_type_id}


def const(value) -> dict:
    return {"type": "constant", "value": value}


def binop(op: str, left: dict, right: dict) -> dict:
    return {"type": "binary_op", "op": op, "left": left, "right": right}


def unary(op: str, operand: dict) -> dict:
    return {"type": "unary_op", "op": op, "operand": operand}


def func(name: str, *args: dict) -> dict:
    return {"type": "function", "name": name, "args": list(args)}


def cmp(op: str, left: dict, right: dict) -> dict:
    return {"type": "comparison", "op": op, "left": left, "right": right}


def cond(condition: dict, then: dict, else_: dict) -> dict:
    return {"type": "conditional", "condition": condition, "then": then, "else": else_}


def build_bmi(*, weight_kg_id: int, height_cm_id: int) -> dict:
    """weight_kg / (height_cm / 100) ^ 2"""
    height_m = binop("/", metric(height_cm_id), const(100))
    return binop("/", metric(weight_kg_id), binop("^", height_m, const(2)))


def _navy_branch(
    *, circumference_diff: dict, height_cm_id: int, a: float, b: float, c: float
) -> dict:
    """495 / (a - b*log10(circumference_diff) + c*log10(height)) - 450"""
    denominator = binop(
        "+",
        binop("-", const(a), binop("*", const(b), func("log10", circumference_diff))),
        binop("*", const(c), func("log10", metric(height_cm_id))),
    )
    return binop("-", binop("/", const(495), denominator), const(450))


def build_body_fat_navy(
    *, waist_cm_id: int, neck_cm_id: int, height_cm_id: int, hip_cm_id: int, sex_id: int
) -> dict:
    male_branch = _navy_branch(
        circumference_diff=binop("-", metric(waist_cm_id), metric(neck_cm_id)),
        height_cm_id=height_cm_id,
        a=1.0324,
        b=0.19077,
        c=0.15456,
    )
    female_branch = _navy_branch(
        circumference_diff=binop(
            "-", binop("+", metric(waist_cm_id), metric(hip_cm_id)), metric(neck_cm_id)
        ),
        height_cm_id=height_cm_id,
        a=1.29579,
        b=0.35004,
        c=0.22100,
    )
    return cond(
        cmp("==", metric(sex_id), const("male")),
        male_branch,
        cond(cmp("==", metric(sex_id), const("female")), female_branch, const(None)),
    )


def build_tdee_mifflin(
    *, weight_kg_id: int, height_cm_id: int, dob_id: int, sex_id: int, activity_level_id: int
) -> dict:
    """BMR (Mifflin-St Jeor, branched on sex) * activity multiplier — the
    multiplier comes straight from the Activity Level choice's numeric_value,
    resolved automatically by `AsOfResolver` when it reads that metric leaf.
    """
    age_years = func("age", metric(dob_id))
    base = binop(
        "+",
        binop("*", const(10), metric(weight_kg_id)),
        binop("*", const(6.25), metric(height_cm_id)),
    )
    base_minus_age = binop("-", base, binop("*", const(5), age_years))
    male_bmr = binop("+", base_minus_age, const(5))
    female_bmr = binop("-", base_minus_age, const(161))

    bmr = cond(
        cmp("==", metric(sex_id), const("male")),
        male_bmr,
        cond(cmp("==", metric(sex_id), const("female")), female_bmr, const(None)),
    )
    return binop("*", bmr, metric(activity_level_id))
