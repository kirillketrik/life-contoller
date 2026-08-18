"""Save-time validation for a `FormulaDefinition.expression`.

Returns a list of stable `FormulaError.code`s (never prose) so the frontend
can map each one to Russian copy independently of whatever English detail we
attach for debugging. Semantics agreed with the user: "missing dependency"
means the referenced metric type doesn't exist (an integrity check) — a
formula may be saved before anyone has logged data for its inputs; the live
preview is what shows "no data yet" for that case, not a save-time rejection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import MetricType
from .dependencies import collect_metric_ids, has_zero_division, transitive_metric_ids
from .nodes import FormulaParseError, parse_node


@dataclass(frozen=True)
class FormulaError:
    code: str
    detail: str = field(default="")


def validate_expression(
    expression: object, *, computed_metric_type_id: int | None
) -> list[FormulaError]:
    try:
        node = parse_node(expression)
    except FormulaParseError as exc:
        return [FormulaError(code="invalid_structure", detail=str(exc))]

    errors: list[FormulaError] = []

    metric_ids = collect_metric_ids(node)
    existing_ids = set(MetricType.objects.filter(id__in=metric_ids).values_list("id", flat=True))
    missing_ids = metric_ids - existing_ids
    if missing_ids:
        errors.append(
            FormulaError(
                code="missing_metric_type",
                detail=f"Unknown metric type id(s): {sorted(missing_ids)}",
            )
        )

    if has_zero_division(node):
        errors.append(FormulaError(code="division_by_zero"))

    if computed_metric_type_id is not None:
        closure = transitive_metric_ids(metric_ids)
        if computed_metric_type_id in closure:
            errors.append(FormulaError(code="circular_reference"))

    return errors
