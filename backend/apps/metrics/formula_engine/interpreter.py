"""Visitor that walks a formula AST and resolves it to a value.

Missing data propagates as `None` at every step (never raises, never
substitutes a default) — matching the metrics layer's existing rule that a
formula with an unresolved input simply has no value yet, same as before this
engine existed.
"""

from __future__ import annotations

import math
from datetime import date

from .nodes import (
    BinaryOpNode,
    ComparisonNode,
    ConditionalNode,
    ConstantNode,
    FunctionNode,
    MetricNode,
    Node,
    UnaryOpNode,
)


class Resolver:
    """Protocol every resolver used with `evaluate_node` must satisfy."""

    at: object  # datetime — the timestamp the formula is being evaluated at

    def resolve(self, metric_type_id: int):
        raise NotImplementedError


def evaluate_node(node: Node, resolver: Resolver):
    if isinstance(node, MetricNode):
        return resolver.resolve(node.metric_type_id)
    if isinstance(node, ConstantNode):
        return node.value
    if isinstance(node, BinaryOpNode):
        return _evaluate_binary(node, resolver)
    if isinstance(node, UnaryOpNode):
        return _evaluate_unary(node, resolver)
    if isinstance(node, FunctionNode):
        return _evaluate_function(node, resolver)
    if isinstance(node, ComparisonNode):
        return _evaluate_comparison(node, resolver)
    if isinstance(node, ConditionalNode):
        condition = evaluate_node(node.condition, resolver)
        if condition is None:
            return None
        return evaluate_node(node.then if condition else node.else_, resolver)
    raise TypeError(f"Unhandled node type: {type(node)!r}")


def _as_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _evaluate_binary(node: BinaryOpNode, resolver: Resolver) -> float | None:
    left = _as_number(evaluate_node(node.left, resolver))
    right = _as_number(evaluate_node(node.right, resolver))
    if left is None or right is None:
        return None
    if node.op == "+":
        return left + right
    if node.op == "-":
        return left - right
    if node.op == "*":
        return left * right
    if node.op == "/":
        return None if right == 0 else left / right
    if node.op == "^":
        try:
            return left**right
        except (ValueError, OverflowError):
            return None
    raise ValueError(f"Unhandled binary op '{node.op}'.")


def _evaluate_unary(node: UnaryOpNode, resolver: Resolver) -> float | None:
    operand = _as_number(evaluate_node(node.operand, resolver))
    if operand is None:
        return None
    if node.op == "sqrt":
        return math.sqrt(operand) if operand >= 0 else None
    if node.op == "abs":
        return abs(operand)
    if node.op == "neg":
        return -operand
    raise ValueError(f"Unhandled unary op '{node.op}'.")


def _age_years(dob_value, at) -> int | None:
    if dob_value is None:
        return None
    try:
        dob = date.fromisoformat(str(dob_value))
    except ValueError:
        return None
    reference = at.date()
    age = reference.year - dob.year - ((reference.month, reference.day) < (dob.month, dob.day))
    return age if age >= 0 else None


def _evaluate_function(node: FunctionNode, resolver: Resolver):
    if node.name == "age":
        return _age_years(evaluate_node(node.args[0], resolver), resolver.at)

    values = [_as_number(evaluate_node(arg, resolver)) for arg in node.args]
    if any(value is None for value in values):
        return None
    if node.name == "min":
        return min(values)
    if node.name == "max":
        return max(values)
    if node.name == "round":
        return round(values[0], int(values[1])) if len(values) == 2 else round(values[0])
    if node.name == "log10":
        return math.log10(values[0]) if values[0] > 0 else None
    raise ValueError(f"Unhandled function '{node.name}'.")


def _evaluate_comparison(node: ComparisonNode, resolver: Resolver) -> bool | None:
    left = evaluate_node(node.left, resolver)
    right = evaluate_node(node.right, resolver)
    if left is None or right is None:
        return None

    left_num, right_num = _as_number(left), _as_number(right)
    if left_num is not None and right_num is not None:
        left, right = left_num, right_num
    else:
        left, right = str(left), str(right)

    if node.op == "==":
        return left == right
    if node.op == "!=":
        return left != right
    if node.op == "<":
        return left < right
    if node.op == ">":
        return left > right
    if node.op == "<=":
        return left <= right
    if node.op == ">=":
        return left >= right
    raise ValueError(f"Unhandled comparison op '{node.op}'.")
