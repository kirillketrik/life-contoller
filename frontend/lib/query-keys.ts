import type { AggregateParams } from "./api";

export const METRIC_TYPES_QUERY_KEY = ["metric-types"] as const;

export const metricTypeQueryKey = (id: number) => ["metric-types", id] as const;

export const metricEntriesQueryKey = (metricTypeId: number) =>
  ["metric-entries", metricTypeId] as const;

export const metricAggregateQueryKey = (metricTypeId: number, params: AggregateParams) =>
  ["metric-aggregate", metricTypeId, params] as const;

/** Prefix key matching every aggregate query (any timeframe/range) for one
 * metric type — pass to `invalidateQueries` after logging/deleting an entry,
 * since the exact params in play at that moment aren't known here. */
export const metricAggregatePrefixKey = (metricTypeId: number) =>
  ["metric-aggregate", metricTypeId] as const;

export const METRIC_THRESHOLDS_QUERY_KEY = ["metric-thresholds"] as const;

export const FORMULA_DEFINITIONS_QUERY_KEY = ["formula-definitions"] as const;
