"use client";

import { DndContext, type DragEndEvent } from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRouter } from "@/i18n/navigation";
import { ApiError, formulaDefinitions, metricTypes } from "@/lib/api";
import { FORMULA_DEFINITIONS_QUERY_KEY, METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";
import type { ComparisonOp } from "@/lib/types";

import { FormulaCanvas } from "./formula-canvas";
import { FormulaPreview } from "./formula-preview";
import { MetricsPalette } from "./metrics-palette";
import { OperatorsPalette } from "./operators-palette";
import { useFormulaBuilder } from "./use-formula-builder";

export function FormulaBuilder() {
  const t = useTranslations("formulaBuilder");
  const router = useRouter();
  const queryClient = useQueryClient();
  const state = useFormulaBuilder();
  const [computedMetricTypeId, setComputedMetricTypeId] = useState("");

  const metricTypesQuery = useQuery({
    queryKey: METRIC_TYPES_QUERY_KEY,
    queryFn: () => metricTypes.list(),
  });
  const allTypes = metricTypesQuery.data?.results ?? [];
  const computedTypes = allTypes.filter((type) => type.is_computed);
  const metricTypesById = new Map(allTypes.map((type) => [type.id, type]));

  const mutation = useMutation({
    mutationFn: formulaDefinitions.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FORMULA_DEFINITIONS_QUERY_KEY });
      toast.success(t("created"));
      router.push("/formulas");
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("createFailed"));
    },
  });

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || over.id !== state.activeKey) return;
    const data = active.data.current as
      | { kind: "metric"; metricTypeId: number }
      | { kind: "operator"; op: string }
      | undefined;
    if (!data) return;

    if (data.kind === "metric") {
      if (!state.insertMetric(data.metricTypeId)) toast.error(t("expectOperand"));
    } else if (data.kind === "operator") {
      const inserted = state.isComparisonSlot
        ? state.insertComparisonOperator(data.op as ComparisonOp)
        : state.insertOperator(data.op);
      if (!inserted) toast.error(state.isComparisonSlot ? t("expectComparisonOperator") : t("expectOperator"));
    }
  }

  function handleSave() {
    if (!computedMetricTypeId) {
      toast.error(t("chooseComputedType"));
      return;
    }
    if (state.ast === null) {
      toast.error(t("incomplete"));
      return;
    }
    mutation.mutate({ computed_metric_type: Number(computedMetricTypeId), expression: state.ast });
  }

  return (
    <div className="space-y-6">
      <div className="max-w-sm space-y-2">
        <Label>{t("computedMetricType")}</Label>
        <Select
          items={Object.fromEntries(computedTypes.map((type) => [String(type.id), type.name]))}
          value={computedMetricTypeId}
          onValueChange={(v) => setComputedMetricTypeId(v ?? "")}
        >
          <SelectTrigger>
            <SelectValue placeholder={t("selectPlaceholder")} />
          </SelectTrigger>
          <SelectContent>
            {computedTypes.map((type) => (
              <SelectItem key={type.id} value={String(type.id)}>
                {type.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {computedTypes.length === 0 && (
          <p className="text-xs text-muted-foreground">{t("createComputedHint")}</p>
        )}
      </div>

      <DndContext onDragEnd={handleDragEnd}>
        <FormulaCanvas state={state} metricTypesById={metricTypesById} />

        <div className="grid gap-4 rounded-md border p-4 md:grid-cols-2">
          <MetricsPalette
            excludeMetricTypeId={computedMetricTypeId ? Number(computedMetricTypeId) : undefined}
            disabled={state.expectedKind !== "operand"}
          />
          <OperatorsPalette state={state} />
        </div>
      </DndContext>

      <FormulaPreview
        state={state}
        metricTypesById={metricTypesById}
        computedMetricTypeId={computedMetricTypeId ? Number(computedMetricTypeId) : null}
      />

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={mutation.isPending || state.ast === null}>
          {mutation.isPending ? t("creating") : t("create")}
        </Button>
      </div>
    </div>
  );
}
