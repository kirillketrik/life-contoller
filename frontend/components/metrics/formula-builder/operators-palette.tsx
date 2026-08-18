"use client";

import { useDraggable } from "@dnd-kit/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { metricTypes } from "@/lib/api";
import { METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";
import { BINARY_OPS, COMPARISON_OPS } from "@/lib/types";
import type { UnaryWrapOp } from "@/lib/formula-builder/tokens";

import type { FormulaBuilderState } from "./use-formula-builder";

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

const WRAP_OPS: readonly UnaryWrapOp[] = ["sqrt", "abs", "round"];
const WRAP_LABELS: Record<UnaryWrapOp, string> = { sqrt: "√", abs: "abs", round: "round" };

interface OperatorsPaletteProps {
  state: FormulaBuilderState;
}

export function OperatorsPalette({ state }: OperatorsPaletteProps) {
  const t = useTranslations("formulaBuilder");
  const operandExpected = state.expectedKind === "operand";
  const operatorExpected = state.expectedKind === "operator";

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground">
          {state.isComparisonSlot ? t("comparisonOperators") : t("operators")}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {(state.isComparisonSlot ? COMPARISON_OPS : BINARY_OPS).map((op) => (
            <OperatorChip key={op} op={op} disabled={!operatorExpected} />
          ))}
        </div>
      </div>

      {!state.isComparisonSlot && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">{t("functions")}</p>
          <div className="flex flex-wrap gap-1.5">
            {WRAP_OPS.map((op) => (
              <Button
                key={op}
                type="button"
                variant="outline"
                size="sm"
                disabled={!operandExpected}
                onClick={() => state.insertUnaryWrap(op)}
              >
                {WRAP_LABELS[op]}
              </Button>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!operandExpected}
              onClick={() => state.insertGroup()}
            >
              ( … )
            </Button>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground">{t("structure")}</p>
        <div className="flex flex-wrap gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!operandExpected}
            onClick={() => state.insertConditional()}
          >
            {t("ifThenElse")}
          </Button>
          <AddConstantDialog state={state} disabled={!operandExpected} />
        </div>
      </div>
    </div>
  );
}

function OperatorChip({ op, disabled }: { op: string; disabled: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `op-${op}`,
    data: { kind: "operator", op },
    disabled,
  });

  return (
    <Badge
      ref={setNodeRef}
      variant="outline"
      className={disabled ? "opacity-40" : `cursor-grab font-mono ${isDragging ? "opacity-50" : ""}`}
      {...listeners}
      {...attributes}
    >
      {OP_SYMBOLS[op] ?? op}
    </Badge>
  );
}

function AddConstantDialog({ state, disabled }: { state: FormulaBuilderState; disabled: boolean }) {
  const t = useTranslations("formulaBuilder");
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"number" | "option">("number");
  const [numberValue, setNumberValue] = useState("");
  const [optionMetricTypeId, setOptionMetricTypeId] = useState("");
  const [optionCode, setOptionCode] = useState("");

  const query = useQuery({ queryKey: METRIC_TYPES_QUERY_KEY, queryFn: () => metricTypes.list() });
  const choiceTypes = (query.data?.results ?? []).filter((type) => type.value_type === "choice");
  const selectedType = choiceTypes.find((type) => String(type.id) === optionMetricTypeId);

  function reset() {
    setMode("number");
    setNumberValue("");
    setOptionMetricTypeId("");
    setOptionCode("");
  }

  function handleAdd() {
    if (mode === "number") {
      if (!numberValue.trim()) return;
      state.insertConstant(Number(numberValue));
    } else {
      if (!optionCode) return;
      state.insertConstant(optionCode);
    }
    reset();
    setOpen(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger render={<Button type="button" variant="outline" size="sm" disabled={disabled} />}>
        {t("addConstant")}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("addConstant")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant={mode === "number" ? "default" : "outline"}
              onClick={() => setMode("number")}
            >
              {t("constantNumber")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant={mode === "option" ? "default" : "outline"}
              onClick={() => setMode("option")}
              disabled={choiceTypes.length === 0}
            >
              {t("constantOption")}
            </Button>
          </div>
          {mode === "number" ? (
            <Input
              type="number"
              step="any"
              value={numberValue}
              onChange={(e) => setNumberValue(e.target.value)}
              placeholder={t("constantNumberPlaceholder")}
            />
          ) : (
            <>
              <Select
                items={Object.fromEntries(choiceTypes.map((type) => [String(type.id), type.name]))}
                value={optionMetricTypeId}
                onValueChange={(v) => {
                  setOptionMetricTypeId(v ?? "");
                  setOptionCode("");
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("constantOptionTypePlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {choiceTypes.map((type) => (
                    <SelectItem key={type.id} value={String(type.id)}>
                      {type.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedType && (
                <Select
                  items={Object.fromEntries(selectedType.choices.map((c) => [c.code, c.label]))}
                  value={optionCode}
                  onValueChange={(v) => setOptionCode(v ?? "")}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t("constantOptionValuePlaceholder")} />
                  </SelectTrigger>
                  <SelectContent>
                    {selectedType.choices.map((choice) => (
                      <SelectItem key={choice.code} value={choice.code}>
                        {choice.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </>
          )}
        </div>
        <DialogFooter>
          <Button type="button" onClick={handleAdd}>
            {t("add")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
