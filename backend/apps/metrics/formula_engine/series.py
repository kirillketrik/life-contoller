"""Single-point and time-series evaluation of a `FormulaDefinition`. Same
contract as the old `apps.metrics.formulas` module this replaces — see
`apps.metrics.selectors.points_for_metric_type`, which calls `computed_series`
without needing to know a metric type is computed vs. stored.
"""

from __future__ import annotations

from datetime import datetime

from ..aggregation import DataPoint
from ..models import FormulaDefinition, MetricEntry, MetricType
from .dependencies import collect_metric_ids, transitive_metric_ids
from .interpreter import evaluate_node
from .nodes import parse_node
from .resolvers import AsOfResolver


def evaluate_formula(formula_definition: FormulaDefinition, *, user, at: datetime):
    node = parse_node(formula_definition.expression)
    return evaluate_node(node, AsOfResolver(user=user, at=at))


def _base_dependency_ids(formula_definition: FormulaDefinition) -> set[int]:
    node = parse_node(formula_definition.expression)
    all_ids = transitive_metric_ids(collect_metric_ids(node))
    return set(
        MetricType.objects.filter(id__in=all_ids, is_computed=False).values_list("id", flat=True)
    )


def computed_series(
    formula_definition: FormulaDefinition, *, user, range_start: datetime, range_end: datetime
) -> list[DataPoint]:
    base_ids = _base_dependency_ids(formula_definition)
    timestamps = set(
        MetricEntry.objects.filter(
            metric_type_id__in=base_ids,
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
