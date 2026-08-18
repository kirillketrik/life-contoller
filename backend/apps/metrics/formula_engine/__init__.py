"""AST-based formula engine for computed `MetricType`s — replaces the old
`apps.metrics.formulas` hardcoded-Python-per-formula module. See `nodes.py`
for the expression schema, `interpreter.py` for the visitor that evaluates
it, `resolvers.py` for how a metric leaf resolves to a value,
`validation.py` for save-time checks, `series.py` for the public
`evaluate_formula`/`computed_series` API `apps.metrics.selectors` calls, and
`builtins.py` for the three seeded built-in formulas.
"""

from .nodes import FormulaParseError, parse_node
from .series import computed_series, evaluate_formula
from .validation import FormulaError, validate_expression

__all__ = [
    "FormulaError",
    "FormulaParseError",
    "computed_series",
    "evaluate_formula",
    "parse_node",
    "validate_expression",
]
