"""Shared metric-type dependency-graph helpers, used by both `validation.py`
(circular-reference / missing-metric checks) and `series.py` (finding which
base metric types drive a formula's historical series).
"""

from __future__ import annotations

from ..models import MetricType
from .nodes import (
    BinaryOpNode,
    ConstantNode,
    FormulaParseError,
    MetricNode,
    Node,
    iter_children,
    parse_node,
)


def collect_metric_ids(node: Node) -> set[int]:
    """Every `MetricNode.metric_type_id` referenced directly in this tree
    (not recursing into computed leaves' own formulas — see
    `transitive_metric_ids` for that)."""
    ids: set[int] = set()

    def walk(n: Node) -> None:
        if isinstance(n, MetricNode):
            ids.add(n.metric_type_id)
        for child in iter_children(n):
            walk(child)

    walk(node)
    return ids


def has_zero_division(node: Node) -> bool:
    """True if the tree contains a `x / 0` with a literal zero divisor —
    the only division-by-zero shape detectable without runtime data."""
    if isinstance(node, BinaryOpNode) and node.op == "/":
        if isinstance(node.right, ConstantNode) and node.right.value == 0:
            return True
    return any(has_zero_division(child) for child in iter_children(node))


def transitive_metric_ids(
    metric_type_ids: set[int], *, visited: set[int] | None = None
) -> set[int]:
    """Expands `metric_type_ids` to include, for every computed metric type
    among them, the metric type ids its own formula references — recursively,
    cycle-guarded via `visited` so a genuine cycle in already-saved data can't
    cause infinite recursion here either.
    """
    visited = visited if visited is not None else set()
    result: set[int] = set()
    metric_types = MetricType.objects.filter(id__in=metric_type_ids).select_related(
        "formula_definition"
    )
    for metric_type in metric_types:
        result.add(metric_type.id)
        if not metric_type.is_computed or metric_type.id in visited:
            continue
        formula_definition = getattr(metric_type, "formula_definition", None)
        if formula_definition is None:
            continue
        visited.add(metric_type.id)
        try:
            node = parse_node(formula_definition.expression)
        except FormulaParseError:
            continue
        result |= transitive_metric_ids(collect_metric_ids(node), visited=visited)
    return result
