"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { formulaDefinitions } from "@/lib/api";
import { renderRussian } from "@/lib/formula-builder/tokens";
import type { MetricType } from "@/lib/types";

import type { FormulaBuilderState } from "./use-formula-builder";

const ERROR_MESSAGE_KEYS: Record<string, string> = {
  invalid_structure: "errorInvalidStructure",
  missing_metric_type: "errorMissingMetricType",
  division_by_zero: "errorDivisionByZero",
  circular_reference: "errorCircularReference",
};

interface FormulaPreviewProps {
  state: FormulaBuilderState;
  metricTypesById: Map<number, MetricType>;
  computedMetricTypeId: number | null;
}

/** Debounces the compiled AST so the preview endpoint isn't hit on every
 * keystroke/drop — only once the expression settles for ~400ms. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function FormulaPreview({ state, metricTypesById, computedMetricTypeId }: FormulaPreviewProps) {
  const t = useTranslations("formulaBuilder");
  const russian = renderRussian(state.root, metricTypesById);
  const debouncedAst = useDebouncedValue(state.ast, 400);

  const previewQuery = useQuery({
    queryKey: ["formula-preview", debouncedAst, computedMetricTypeId],
    queryFn: () => formulaDefinitions.preview(debouncedAst!, computedMetricTypeId ?? undefined),
    enabled: debouncedAst !== null,
  });

  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-4">
      <p className="text-xs font-medium text-muted-foreground">{t("previewLabel")}</p>
      <p className="font-mono text-sm">{russian || t("emptyCanvas")}</p>
      {state.ast === null ? (
        <p className="text-sm text-muted-foreground">{t("incomplete")}</p>
      ) : previewQuery.isFetching ? (
        <p className="text-sm text-muted-foreground">{t("computing")}</p>
      ) : previewQuery.data && previewQuery.data.errors.length > 0 ? (
        <ul className="space-y-1 text-sm text-destructive">
          {previewQuery.data.errors.map((error, i) => (
            <li key={i}>{t(ERROR_MESSAGE_KEYS[error.code] ?? "errorUnknown")}</li>
          ))}
        </ul>
      ) : (
        <p className="text-lg font-semibold">
          {previewQuery.data?.value === null || previewQuery.data?.value === undefined
            ? t("noDataYet")
            : String(previewQuery.data.value)}
        </p>
      )}
    </div>
  );
}

export function isFormulaSaveable(state: FormulaBuilderState): boolean {
  return state.ast !== null;
}
