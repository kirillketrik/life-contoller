"use client";

import { useDroppable } from "@dnd-kit/core";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { MetricType } from "@/lib/types";

import type { FormulaBuilderState } from "./use-formula-builder";
import type { FlatToken } from "@/lib/formula-builder/tokens";

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

function chipLabel(token: FlatToken, metricTypesById: Map<number, MetricType>): string {
  switch (token.kind) {
    case "metric":
      return metricTypesById.get(token.metricTypeId)?.name ?? `#${token.metricTypeId}`;
    case "constant":
      return typeof token.value === "string" ? `«${token.value}»` : String(token.value);
    case "operator":
      return OP_SYMBOLS[token.op] ?? token.op;
    case "group":
      return "(…)";
    case "unaryWrap":
      return `${token.op === "sqrt" ? "√" : token.op}(…)`;
    case "conditional":
      return "если / то / иначе";
  }
}

interface FormulaCanvasProps {
  state: FormulaBuilderState;
  metricTypesById: Map<number, MetricType>;
}

export function FormulaCanvas({ state, metricTypesById }: FormulaCanvasProps) {
  const t = useTranslations("formulaBuilder");
  const { setNodeRef, isOver } = useDroppable({ id: state.activeKey });

  return (
    <div className="space-y-2">
      <Breadcrumb state={state} />
      <div
        ref={setNodeRef}
        className={cn(
          "flex min-h-16 flex-wrap items-center gap-2 rounded-md border-2 border-dashed p-3 transition-colors",
          isOver ? "border-primary bg-primary/5" : "border-border",
        )}
      >
        {state.activeTokens.length === 0 && (
          <span className="text-sm text-muted-foreground">{t("emptyCanvas")}</span>
        )}
        {state.activeTokens.map((token, index) => (
          <Chip
            key={token.id}
            token={token}
            index={index}
            state={state}
            metricTypesById={metricTypesById}
          />
        ))}
        <span className="text-xs text-muted-foreground">
          {state.expectedKind === "operand"
            ? t("expectOperand")
            : state.expectedKind === "operator"
              ? t("expectOperator")
              : t("slotFull")}
        </span>
      </div>
    </div>
  );
}

function Chip({
  token,
  index,
  state,
  metricTypesById,
}: {
  token: FlatToken;
  index: number;
  state: FormulaBuilderState;
  metricTypesById: Map<number, MetricType>;
}) {
  const isContainer =
    token.kind === "group" || token.kind === "unaryWrap" || token.kind === "conditional";

  return (
    <Badge
      variant={isContainer ? "outline" : "secondary"}
      className={cn("gap-1.5 py-1.5 pl-2.5 pr-1.5 text-sm", isContainer && "cursor-pointer")}
      onClick={isContainer ? () => focusInto(token, index, state) : undefined}
    >
      {chipLabel(token, metricTypesById)}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-4"
        onClick={(e) => {
          e.stopPropagation();
          state.removeToken(token.id);
        }}
      >
        <X className="size-3" />
      </Button>
    </Badge>
  );
}

function focusInto(token: FlatToken, index: number, state: FormulaBuilderState) {
  if (token.kind === "group" || token.kind === "unaryWrap") {
    // reach into the hook's setActivePath indirectly by simulating the same
    // insertion path shape it already produces for freshly-inserted containers
    state.focusIntoExisting(index, "tokens");
  } else if (token.kind === "conditional") {
    state.focusIntoExisting(index, "condition");
  }
}

function Breadcrumb({ state }: { state: FormulaBuilderState }) {
  const t = useTranslations("formulaBuilder");
  const segments = state.activePath;

  return (
    <div className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
      <button
        type="button"
        className={cn("hover:underline", segments.length === 0 && "font-medium text-foreground")}
        onClick={() => state.focusToRoot()}
      >
        {t("root")}
      </button>
      {segments.map((seg, i) => (
        <span key={i} className="flex items-center gap-1">
          <span>/</span>
          <button
            type="button"
            className={cn("hover:underline", i === segments.length - 1 && "font-medium text-foreground")}
            onClick={() => state.focusToDepth(i + 1)}
          >
            {seg.slot === "condition" ? t("slotCondition") : seg.slot === "then" ? t("slotThen") : seg.slot === "else" ? t("slotElse") : t("slotGroup")}
          </button>
          {i === segments.length - 1 && seg.slot !== "tokens" && (
            <span className="ml-1 flex gap-1">
              {(["condition", "then", "else"] as const).map((slot) => (
                <button
                  key={slot}
                  type="button"
                  className={cn(
                    "rounded px-1.5 py-0.5 text-xs",
                    seg.slot === slot ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-muted/70",
                  )}
                  onClick={() => state.focusSibling(slot)}
                >
                  {slot === "condition" ? t("slotCondition") : slot === "then" ? t("slotThen") : t("slotElse")}
                </button>
              ))}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}
