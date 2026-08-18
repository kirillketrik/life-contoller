"use client";

import { useMemo, useState } from "react";

import {
  compileToAst,
  type FlatToken,
  getTokensAtPath,
  newTokenId,
  nextExpectedKind,
  pathKey,
  setTokensAtPath,
  type Slot,
  type TokenPath,
  type UnaryWrapOp,
} from "@/lib/formula-builder/tokens";
import type { ComparisonOp, FormulaNode } from "@/lib/types";

/** Drives the visual builder's editing state. Editing is "drill-in": adding a
 * group/function-wrap/conditional inserts an (initially empty) container at
 * the current position and immediately focuses into it — the same way the
 * conditional's condition/then/else slots work — rather than a free-form
 * "select a range of chips and wrap them" interaction, which is a much
 * larger amount of selection-state UI for the same structural outcome.
 * Breadcrumb navigation (`focusUp`/`focusSibling`) moves back out.
 */
export function useFormulaBuilder() {
  const [root, setRoot] = useState<FlatToken[]>([]);
  const [activePath, setActivePath] = useState<TokenPath>([]);

  const activeTokens = getTokensAtPath(root, activePath);
  const isComparisonSlot = activePath.length > 0 && activePath[activePath.length - 1].slot === "condition";
  const expectedKind = nextExpectedKind(activeTokens, isComparisonSlot);
  const activeKey = pathKey(activePath);
  const ast: FormulaNode | null = useMemo(() => compileToAst(root), [root]);

  function mutateActive(updater: (tokens: FlatToken[]) => FlatToken[]) {
    setRoot((prev) => setTokensAtPath(prev, activePath, updater));
  }

  function insertMetric(metricTypeId: number): boolean {
    if (expectedKind !== "operand") return false;
    mutateActive((tokens) => [...tokens, { id: newTokenId(), kind: "metric", metricTypeId }]);
    return true;
  }

  function insertConstant(value: number | string): boolean {
    if (expectedKind !== "operand") return false;
    mutateActive((tokens) => [...tokens, { id: newTokenId(), kind: "constant", value }]);
    return true;
  }

  function insertOperator(op: string): boolean {
    if (expectedKind !== "operator" || isComparisonSlot) return false;
    mutateActive((tokens) => [...tokens, { id: newTokenId(), kind: "operator", op } as FlatToken]);
    return true;
  }

  function insertComparisonOperator(op: ComparisonOp): boolean {
    if (expectedKind !== "operator" || !isComparisonSlot) return false;
    mutateActive((tokens) => [...tokens, { id: newTokenId(), kind: "operator", op }]);
    return true;
  }

  function insertGroup(): boolean {
    if (expectedKind !== "operand") return false;
    const insertIndex = activeTokens.length;
    mutateActive((tokens) => [...tokens, { id: newTokenId(), kind: "group", tokens: [] }]);
    setActivePath((prev) => [...prev, { index: insertIndex, slot: "tokens" }]);
    return true;
  }

  function insertUnaryWrap(op: UnaryWrapOp): boolean {
    if (expectedKind !== "operand") return false;
    const insertIndex = activeTokens.length;
    mutateActive((tokens) => [...tokens, { id: newTokenId(), kind: "unaryWrap", op, tokens: [] }]);
    setActivePath((prev) => [...prev, { index: insertIndex, slot: "tokens" }]);
    return true;
  }

  function insertConditional(): boolean {
    if (expectedKind !== "operand") return false;
    const insertIndex = activeTokens.length;
    mutateActive((tokens) => [
      ...tokens,
      { id: newTokenId(), kind: "conditional", condition: [], then: [], else: [] },
    ]);
    setActivePath((prev) => [...prev, { index: insertIndex, slot: "condition" }]);
    return true;
  }

  function removeToken(id: string) {
    function removeFrom(tokens: FlatToken[]): FlatToken[] {
      return tokens
        .filter((t) => t.id !== id)
        .map((t) => {
          if (t.kind === "group" || t.kind === "unaryWrap") return { ...t, tokens: removeFrom(t.tokens) };
          if (t.kind === "conditional") {
            return {
              ...t,
              condition: removeFrom(t.condition),
              then: removeFrom(t.then),
              else: removeFrom(t.else),
            };
          }
          return t;
        });
    }
    setRoot((prev) => removeFrom(prev));
    setActivePath([]);
  }

  function focusUp() {
    setActivePath((prev) => prev.slice(0, -1));
  }

  function focusSibling(slot: Slot) {
    setActivePath((prev) => {
      if (prev.length === 0) return prev;
      const copy = [...prev];
      copy[copy.length - 1] = { ...copy[copy.length - 1], slot };
      return copy;
    });
  }

  /** Drills into an existing group/unaryWrap ("tokens") or conditional
   * ("condition", as the default first slot) chip that's already in the
   * active canvas — used when clicking a container chip, as opposed to
   * `insertGroup`/`insertUnaryWrap`/`insertConditional`, which create a new
   * one and focus into it. */
  function focusIntoExisting(index: number, slot: Slot) {
    setActivePath((prev) => [...prev, { index, slot }]);
  }

  function focusToRoot() {
    setActivePath([]);
  }

  function focusToDepth(depth: number) {
    setActivePath((prev) => prev.slice(0, depth));
  }

  return {
    root,
    activePath,
    activeTokens,
    activeKey,
    isComparisonSlot,
    expectedKind,
    ast,
    insertMetric,
    insertConstant,
    insertOperator,
    insertComparisonOperator,
    insertGroup,
    insertUnaryWrap,
    insertConditional,
    removeToken,
    focusUp,
    focusSibling,
    focusIntoExisting,
    focusToRoot,
    focusToDepth,
  };
}

export type FormulaBuilderState = ReturnType<typeof useFormulaBuilder>;
