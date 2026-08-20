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

export const DASHBOARD_SUMMARY_QUERY_KEY = ["dashboard-summary"] as const;

export const DASHBOARD_ELEMENTS_QUERY_KEY = ["dashboard-elements"] as const;

export const metricImportSettingsQueryKey = (metricTypeId: number) =>
  ["metric-import-settings", metricTypeId] as const;

export const NUTRIENT_TYPES_QUERY_KEY = ["nutrient-types"] as const;

export const FOOD_ITEMS_QUERY_KEY = ["food-items"] as const;

export const foodItemsQueryKey = (search?: string) => ["food-items", search ?? ""] as const;

export const RECIPES_QUERY_KEY = ["recipes"] as const;

export const recipesQueryKey = (search?: string) => ["recipes", search ?? ""] as const;

export const MEAL_ENTRIES_QUERY_KEY = ["meal-entries"] as const;

export const mealEntriesQueryKey = (date?: string) => ["meal-entries", date ?? ""] as const;
