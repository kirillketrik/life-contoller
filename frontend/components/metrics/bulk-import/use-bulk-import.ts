"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { metricImportSettings } from "@/lib/api";
import {
  metricAggregatePrefixKey,
  metricEntriesQueryKey,
  metricImportSettingsQueryKey,
} from "@/lib/query-keys";
import type { BulkImportDuplicatePolicy, MetricType } from "@/lib/types";
import {
  type BulkImportField,
  type ParsedImportLine,
  extractBulkImportTemplateFields,
  parseImportText,
} from "@/lib/metric-bulk-parse";

const DEFAULT_DATE_FORMAT = "%d.%m.%Y";
const DEFAULT_SEPARATOR = " ";

export interface BulkImportFormState {
  template: string;
  separator: string;
  dateFormat: string;
  decimalSeparator: "." | ",";
  duplicatePolicy: BulkImportDuplicatePolicy;
}

function defaultFormState(): BulkImportFormState {
  return {
    template: "",
    separator: DEFAULT_SEPARATOR,
    dateFormat: DEFAULT_DATE_FORMAT,
    decimalSeparator: ".",
    duplicatePolicy: "skip",
  };
}

/** Everything the bulk metric-entry import page needs, in one hook: the
 * selected target metric type, the template-builder form state (seeded from
 * the user's saved per-metric-type default when one exists), the raw
 * pasted/uploaded text, and the client-side positional parse of that text
 * into `{value, date}` rows — mirrors the `use-formula-builder` convention of
 * keeping state/derivation out of the presentational components. */
export function useBulkImport(metricTypes: MetricType[]) {
  const queryClient = useQueryClient();
  const [metricTypeId, setMetricTypeId] = useState<number | null>(null);
  const [form, setForm] = useState<BulkImportFormState>(defaultFormState());
  const [advancedMode, setAdvancedMode] = useState(false);
  const [rawText, setRawText] = useState("");
  // The metric type id the form was last seeded for — lets the form be
  // (re)seeded from the fetched saved settings the moment they arrive,
  // without a `useEffect` doing the setState (React's "adjust state during
  // render" pattern instead of syncing via an Effect).
  const [seededForId, setSeededForId] = useState<number | null>(null);

  const metricType = metricTypes.find((type) => type.id === metricTypeId) ?? null;

  const savedSettingsQuery = useQuery({
    queryKey: metricTypeId ? metricImportSettingsQueryKey(metricTypeId) : ["metric-import-settings", "none"],
    queryFn: () => metricImportSettings.get(metricTypeId as number),
    enabled: metricTypeId !== null,
  });

  const readyToSeed = metricTypeId === null || savedSettingsQuery.isFetched;
  if (readyToSeed && seededForId !== metricTypeId) {
    setSeededForId(metricTypeId);
    const saved = savedSettingsQuery.data;
    setForm(
      saved
        ? {
            template: saved.template,
            separator: saved.separator,
            dateFormat: saved.date_format,
            decimalSeparator: saved.decimal_separator === "," ? "," : ".",
            duplicatePolicy: "skip",
          }
        : defaultFormState(),
    );
  }

  function selectMetricType(id: number | null) {
    setMetricTypeId(id);
    setRawText("");
  }

  const fields: BulkImportField[] = extractBulkImportTemplateFields(form.template);
  const parsedRows: ParsedImportLine[] = rawText.trim()
    ? parseImportText(rawText, fields, form.separator)
    : [];

  function invalidateAfterImport() {
    if (metricTypeId === null) return;
    queryClient.invalidateQueries({ queryKey: metricEntriesQueryKey(metricTypeId) });
    queryClient.invalidateQueries({ queryKey: metricAggregatePrefixKey(metricTypeId) });
  }

  function invalidateSettings() {
    if (metricTypeId === null) return;
    queryClient.invalidateQueries({ queryKey: metricImportSettingsQueryKey(metricTypeId) });
  }

  return {
    metricTypeId,
    metricType,
    selectMetricType,
    form,
    setForm,
    advancedMode,
    setAdvancedMode,
    rawText,
    setRawText,
    fields,
    parsedRows,
    invalidateAfterImport,
    invalidateSettings,
  };
}
