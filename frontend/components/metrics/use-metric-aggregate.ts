"use client";

import { useQuery } from "@tanstack/react-query";

import { metricAggregate } from "@/lib/api";
import { rangePreset } from "@/lib/metric-range-presets";
import { metricAggregateQueryKey } from "@/lib/query-keys";

/** Fetches OHLC-bucketed data for a metric type over a preset range key
 * (see `RANGE_PRESETS`) — used by the metric detail page's own range
 * picker (dashboard element blocks read their series from the batched
 * `/api/dashboard-elements/` response instead, not this hook). */
export function useMetricAggregate(metricTypeId: number, rangeKey: string, enabled = true) {
  const preset = rangePreset(rangeKey);
  const params = {
    timeframeUnit: preset.timeframeUnit,
    timeframeCount: preset.timeframeCount,
    relativeDays: preset.relativeDays,
  };
  return useQuery({
    queryKey: metricAggregateQueryKey(metricTypeId, params),
    queryFn: () => metricAggregate.get(metricTypeId, params),
    enabled,
  });
}
