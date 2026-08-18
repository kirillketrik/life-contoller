import type { BinaryOp, ComparisonOp, FormulaNode, MetricType } from "@/lib/types";

/** The formula builder's working representation: a flat, linear sequence of
 * chips that's easy to render as a row and to constrain drop targets on —
 * compiled into the tree-shaped `FormulaNode` AST only at the API boundary
 * (preview/save). Each canvas (root, or a group/wrap/conditional slot) is
 * its own `FlatToken[]`, alternating operand/operator/operand/...
 *
 * Scope for this pass: the palette exposes arithmetic operators (+ − × ÷ ^),
 * unary function wraps (√ abs round), grouping, and if/then/else — the
 * multi-argument `min`/`max` function nodes the engine supports are reachable
 * by hand-authoring a `FormulaDefinition.expression` directly, not from this
 * visual palette yet (same "not built this pass" scope-note the plan already
 * carries for edit-in-builder).
 */

export type UnaryWrapOp = "sqrt" | "abs" | "round";
export const UNARY_WRAP_OPS: readonly UnaryWrapOp[] = ["sqrt", "abs", "round"];

let nextId = 0;
export function newTokenId(): string {
  nextId += 1;
  return `t${nextId}`;
}

export type FlatToken =
  | { id: string; kind: "metric"; metricTypeId: number }
  | { id: string; kind: "constant"; value: number | string }
  | { id: string; kind: "operator"; op: BinaryOp | ComparisonOp }
  | { id: string; kind: "group"; tokens: FlatToken[] }
  | { id: string; kind: "unaryWrap"; op: UnaryWrapOp; tokens: FlatToken[] }
  | { id: string; kind: "conditional"; condition: FlatToken[]; then: FlatToken[]; else: FlatToken[] };

export type Slot = "tokens" | "condition" | "then" | "else";
export interface PathSegment {
  index: number;
  slot: Slot;
}
export type TokenPath = PathSegment[];

export function pathKey(path: TokenPath): string {
  return path.length === 0 ? "root" : path.map((s) => `${s.slot}:${s.index}`).join("/");
}

export function getTokensAtPath(root: FlatToken[], path: TokenPath): FlatToken[] {
  let current = root;
  for (const seg of path) {
    const token = current[seg.index];
    if (!token) return current;
    if (seg.slot === "tokens" && (token.kind === "group" || token.kind === "unaryWrap")) {
      current = token.tokens;
    } else if (token.kind === "conditional" && seg.slot !== "tokens") {
      current = token[seg.slot];
    } else {
      return current;
    }
  }
  return current;
}

export function setTokensAtPath(
  root: FlatToken[],
  path: TokenPath,
  updater: (tokens: FlatToken[]) => FlatToken[],
): FlatToken[] {
  if (path.length === 0) return updater(root);
  const [seg, ...rest] = path;
  return root.map((token, i) => {
    if (i !== seg.index) return token;
    if (seg.slot === "tokens" && (token.kind === "group" || token.kind === "unaryWrap")) {
      return { ...token, tokens: setTokensAtPath(token.tokens, rest, updater) };
    }
    if (token.kind === "conditional" && seg.slot !== "tokens") {
      return { ...token, [seg.slot]: setTokensAtPath(token[seg.slot], rest, updater) };
    }
    return token;
  });
}

export type ExpectedKind = "operand" | "operator" | "full";

export function nextExpectedKind(tokens: FlatToken[], isComparisonSlot: boolean): ExpectedKind {
  if (isComparisonSlot && tokens.length >= 3) return "full";
  return tokens.length % 2 === 0 ? "operand" : "operator";
}

function compileAtom(token: FlatToken): FormulaNode | null {
  switch (token.kind) {
    case "metric":
      return { type: "metric", metric_type_id: token.metricTypeId };
    case "constant":
      return { type: "constant", value: token.value };
    case "group":
      return compileSequence(token.tokens);
    case "unaryWrap": {
      const inner = compileSequence(token.tokens);
      if (!inner) return null;
      if (token.op === "sqrt" || token.op === "abs") {
        return { type: "unary_op", op: token.op, operand: inner };
      }
      return { type: "function", name: token.op, args: [inner] };
    }
    case "conditional": {
      const condition = compileComparison(token.condition);
      const then = compileSequence(token.then);
      const elseNode = compileSequence(token.else);
      if (!condition || !then || !elseNode) return null;
      return { type: "conditional", condition, then, else: elseNode };
    }
    case "operator":
      return null;
  }
}

function compileComparison(tokens: FlatToken[]): FormulaNode | null {
  if (tokens.length !== 3) return null;
  const [left, opToken, right] = tokens;
  if (opToken.kind !== "operator") return null;
  const leftNode = compileAtom(left);
  const rightNode = compileAtom(right);
  if (!leftNode || !rightNode) return null;
  return { type: "comparison", op: opToken.op as ComparisonOp, left: leftNode, right: rightNode };
}

function combineByPrecedence(operands: FormulaNode[], ops: BinaryOp[]): FormulaNode {
  const vals = [...operands];
  const opsArr = [...ops];

  for (let i = opsArr.length - 1; i >= 0; i--) {
    if (opsArr[i] === "^") {
      vals.splice(i, 2, { type: "binary_op", op: "^", left: vals[i], right: vals[i + 1] });
      opsArr.splice(i, 1);
    }
  }
  for (let i = 0; i < opsArr.length; ) {
    if (opsArr[i] === "*" || opsArr[i] === "/") {
      vals.splice(i, 2, { type: "binary_op", op: opsArr[i], left: vals[i], right: vals[i + 1] });
      opsArr.splice(i, 1);
    } else {
      i++;
    }
  }
  for (let i = 0; i < opsArr.length; ) {
    vals.splice(i, 2, { type: "binary_op", op: opsArr[i], left: vals[i], right: vals[i + 1] });
    opsArr.splice(i, 1);
  }
  return vals[0];
}

function compileSequence(tokens: FlatToken[]): FormulaNode | null {
  if (tokens.length === 0 || tokens.length % 2 === 0) return null;
  const operands: FormulaNode[] = [];
  const ops: BinaryOp[] = [];
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (i % 2 === 0) {
      const node = compileAtom(token);
      if (!node) return null;
      operands.push(node);
    } else {
      if (token.kind !== "operator" || !["+", "-", "*", "/", "^"].includes(token.op)) return null;
      ops.push(token.op as BinaryOp);
    }
  }
  return combineByPrecedence(operands, ops);
}

/** Compiles the root token sequence to a `FormulaNode`, or `null` if the
 * expression is structurally incomplete (a dangling operand/operator slot
 * anywhere in the tree) — callers use `null` to disable Save and show "—"
 * in the live preview rather than sending a malformed expression. */
export function compileToAst(tokens: FlatToken[]): FormulaNode | null {
  return compileSequence(tokens);
}

const OP_SYMBOLS: Record<string, string> = {
  "+": "+",
  "-": "−",
  "*": "×",
  "/": "÷",
  "^": "^",
  "==": "=",
  "!=": "≠",
  "<": "<",
  ">": ">",
  "<=": "≤",
  ">=": "≥",
};

const WRAP_LABELS: Record<UnaryWrapOp, string> = { sqrt: "√", abs: "abs", round: "round" };

export function renderRussian(tokens: FlatToken[], metricTypesById: Map<number, MetricType>): string {
  if (tokens.length === 0) return "";
  return tokens.map((token) => renderToken(token, metricTypesById)).join(" ");
}

function renderToken(token: FlatToken, byId: Map<number, MetricType>): string {
  switch (token.kind) {
    case "metric":
      return byId.get(token.metricTypeId)?.name ?? `#${token.metricTypeId}`;
    case "constant":
      return typeof token.value === "string" ? `«${token.value}»` : String(token.value);
    case "operator":
      return OP_SYMBOLS[token.op] ?? token.op;
    case "group":
      return `(${renderRussian(token.tokens, byId)})`;
    case "unaryWrap":
      return `${WRAP_LABELS[token.op]}(${renderRussian(token.tokens, byId)})`;
    case "conditional":
      return `если ${renderRussian(token.condition, byId)} то ${renderRussian(token.then, byId)} иначе ${renderRussian(token.else, byId)}`;
  }
}
