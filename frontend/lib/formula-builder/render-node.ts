import type { FormulaNode, MetricType } from "@/lib/types";

const BINARY_SYMBOLS: Record<string, string> = { "+": "+", "-": "−", "*": "×", "/": "÷", "^": "^" };
const COMPARISON_SYMBOLS: Record<string, string> = {
  "==": "=",
  "!=": "≠",
  "<": "<",
  ">": ">",
  "<=": "≤",
  ">=": "≥",
};

/** Read-only Russian rendering of a saved `FormulaNode` tree — walks the AST
 * directly and substitutes each metric leaf with its Russian `name`, per the
 * "no separate variable-legend block" goal. Distinct from the builder's
 * `FlatToken`-based `renderRussian` (used while editing): this operates on
 * the tree shape the API actually returns, no round-trip through the flat
 * token model needed for a read-only display like the formulas list page.
 *
 * Nested `binary_op`/`comparison` children are always wrapped in parentheses
 * (rather than only when operator precedence requires it) — flat text with
 * precedence-dependent grouping is easy to misread at a glance, and this
 * guarantees the displayed formula can never be read with the wrong grouping.
 */
export function renderFormulaNodeRussian(node: FormulaNode, metricTypesById: Map<number, MetricType>): string {
  return renderNode(node, metricTypesById, true);
}

function renderNode(node: FormulaNode, byId: Map<number, MetricType>, isTopLevel: boolean): string {
  switch (node.type) {
    case "metric":
      return byId.get(node.metric_type_id)?.name ?? `#${node.metric_type_id}`;
    case "constant":
      return typeof node.value === "string" ? `«${node.value}»` : String(node.value);
    case "binary_op": {
      const text = `${renderNode(node.left, byId, false)} ${BINARY_SYMBOLS[node.op]} ${renderNode(node.right, byId, false)}`;
      return isTopLevel ? text : `(${text})`;
    }
    case "unary_op": {
      const label = node.op === "sqrt" ? "√" : node.op;
      return `${label}(${renderNode(node.operand, byId, true)})`;
    }
    case "function":
      return `${node.name}(${node.args.map((arg) => renderNode(arg, byId, true)).join(", ")})`;
    case "comparison": {
      const text = `${renderNode(node.left, byId, false)} ${COMPARISON_SYMBOLS[node.op]} ${renderNode(node.right, byId, false)}`;
      return isTopLevel ? text : `(${text})`;
    }
    case "conditional":
      return `если ${renderNode(node.condition, byId, true)} то ${renderNode(node.then, byId, true)} иначе ${renderNode(node.else, byId, true)}`;
  }
}
