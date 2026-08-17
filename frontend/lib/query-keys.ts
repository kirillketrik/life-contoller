export const METRIC_TYPES_QUERY_KEY = ["metric-types"] as const;

export const metricTypeQueryKey = (id: number) => ["metric-types", id] as const;

export const metricEntriesQueryKey = (metricTypeId: number) =>
  ["metric-entries", metricTypeId] as const;
