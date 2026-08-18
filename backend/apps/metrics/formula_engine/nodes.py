"""AST node types for a `FormulaDefinition.expression` and the strict parser
that turns the stored JSON dict into typed nodes.

Deliberately not `eval`/string-expression based (injection + correctness
risk) — the builder UI composes this tree visually, `parse_node` validates it
defensively at the API boundary, and `formula_engine.interpreter` walks it.
"""

from __future__ import annotations

from dataclasses import dataclass

BINARY_OPS = frozenset({"+", "-", "*", "/", "^"})
UNARY_OPS = frozenset({"sqrt", "abs", "neg"})
COMPARISON_OPS = frozenset({"==", "!=", "<", ">", "<=", ">="})

# function name -> (min args, max args | None for unbounded).
# `age` and `log10` are engine additions beyond the builder's basic palette
# (sqrt/min/max/abs/round): `age` replaces the old formulas.py dob-special-case
# (TDEE needs age-from-date-of-birth), `log10` is required to reproduce the
# Navy body-fat % formula. Both are ordinary function nodes to the engine.
FUNCTION_ARITY: dict[str, tuple[int, int | None]] = {
    "min": (2, None),
    "max": (2, None),
    "round": (1, 2),
    "age": (1, 1),
    "log10": (1, 1),
}

CONSTANT_TYPES = (int, float, str, bool, type(None))


class FormulaParseError(ValueError):
    pass


@dataclass(frozen=True)
class MetricNode:
    metric_type_id: int


@dataclass(frozen=True)
class ConstantNode:
    value: float | str | bool | None


@dataclass(frozen=True)
class BinaryOpNode:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class UnaryOpNode:
    op: str
    operand: Node


@dataclass(frozen=True)
class FunctionNode:
    name: str
    args: tuple[Node, ...]


@dataclass(frozen=True)
class ComparisonNode:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class ConditionalNode:
    condition: Node
    then: Node
    else_: Node


Node = (
    MetricNode
    | ConstantNode
    | BinaryOpNode
    | UnaryOpNode
    | FunctionNode
    | ComparisonNode
    | ConditionalNode
)


def parse_node(raw: object) -> Node:
    if not isinstance(raw, dict):
        raise FormulaParseError("Expected a node object.")
    node_type = raw.get("type")

    if node_type == "metric":
        metric_type_id = raw.get("metric_type_id")
        if not isinstance(metric_type_id, int) or isinstance(metric_type_id, bool):
            raise FormulaParseError("'metric' node requires an integer metric_type_id.")
        return MetricNode(metric_type_id=metric_type_id)

    if node_type == "constant":
        if "value" not in raw:
            raise FormulaParseError("'constant' node requires a value.")
        value = raw["value"]
        if not isinstance(value, CONSTANT_TYPES):
            raise FormulaParseError("'constant' value must be a number, string, boolean, or null.")
        return ConstantNode(value=value)

    if node_type == "binary_op":
        op = raw.get("op")
        if op not in BINARY_OPS:
            raise FormulaParseError(f"Unknown binary operator '{op}'.")
        return BinaryOpNode(
            op=op, left=parse_node(raw.get("left")), right=parse_node(raw.get("right"))
        )

    if node_type == "unary_op":
        op = raw.get("op")
        if op not in UNARY_OPS:
            raise FormulaParseError(f"Unknown unary operator '{op}'.")
        return UnaryOpNode(op=op, operand=parse_node(raw.get("operand")))

    if node_type == "function":
        name = raw.get("name")
        arity = FUNCTION_ARITY.get(name)
        if arity is None:
            raise FormulaParseError(f"Unknown function '{name}'.")
        args_raw = raw.get("args")
        if not isinstance(args_raw, list):
            raise FormulaParseError(f"Function '{name}' requires an args list.")
        min_args, max_args = arity
        if len(args_raw) < min_args or (max_args is not None and len(args_raw) > max_args):
            raise FormulaParseError(f"Function '{name}' got the wrong number of arguments.")
        return FunctionNode(name=name, args=tuple(parse_node(arg) for arg in args_raw))

    if node_type == "comparison":
        op = raw.get("op")
        if op not in COMPARISON_OPS:
            raise FormulaParseError(f"Unknown comparison operator '{op}'.")
        return ComparisonNode(
            op=op, left=parse_node(raw.get("left")), right=parse_node(raw.get("right"))
        )

    if node_type == "conditional":
        return ConditionalNode(
            condition=parse_node(raw.get("condition")),
            then=parse_node(raw.get("then")),
            else_=parse_node(raw.get("else")),
        )

    raise FormulaParseError(f"Unknown node type '{node_type}'.")


def iter_children(node: Node):
    if isinstance(node, MetricNode | ConstantNode):
        return
    if isinstance(node, BinaryOpNode):
        yield node.left
        yield node.right
    elif isinstance(node, UnaryOpNode):
        yield node.operand
    elif isinstance(node, FunctionNode):
        yield from node.args
    elif isinstance(node, ComparisonNode):
        yield node.left
        yield node.right
    elif isinstance(node, ConditionalNode):
        yield node.condition
        yield node.then
        yield node.else_
