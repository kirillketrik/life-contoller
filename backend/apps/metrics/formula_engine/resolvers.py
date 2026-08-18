"""Resolves a `MetricNode`'s value for a user as of a given timestamp."""

from __future__ import annotations

from datetime import datetime

from ..models import MetricEntry, MetricType, MetricTypeChoice, ValueType
from .interpreter import evaluate_node
from .nodes import parse_node


class AsOfResolver:
    """Non-computed metric type: most-recent `MetricEntry.value` at/before
    `at`, with choice-valued metrics resolved to their `numeric_value` (if
    set) or `code` (otherwise) — this is what lets Activity Level resolve as
    a number and Sex resolve as a comparable string, with no extra AST
    concept needed. Computed metric type: recursively evaluate its own
    `FormulaDefinition.expression` at the same `at`, cycle-guarded.
    """

    def __init__(self, *, user, at: datetime):
        self.user = user
        self.at = at
        self._visiting: set[int] = set()

    def resolve(self, metric_type_id: int):
        metric_type = MetricType.objects.filter(id=metric_type_id).first()
        if metric_type is None:
            return None
        if metric_type.is_computed:
            return self._resolve_computed(metric_type)
        return self._resolve_base(metric_type)

    def _resolve_computed(self, metric_type: MetricType):
        if metric_type.id in self._visiting:
            return None
        formula_definition = getattr(metric_type, "formula_definition", None)
        if formula_definition is None:
            return None
        self._visiting.add(metric_type.id)
        try:
            node = parse_node(formula_definition.expression)
            return evaluate_node(node, self)
        finally:
            self._visiting.discard(metric_type.id)

    def _resolve_base(self, metric_type: MetricType):
        entry = (
            MetricEntry.objects.filter(
                metric_type=metric_type, owner=self.user, recorded_at__lte=self.at
            )
            .order_by("-recorded_at")
            .first()
        )
        if entry is None:
            return None
        if metric_type.value_type == ValueType.CHOICE:
            option = MetricTypeChoice.objects.filter(
                metric_type=metric_type, code=entry.value
            ).first()
            if option is None:
                return None
            return option.numeric_value if option.numeric_value is not None else option.code
        return entry.value
