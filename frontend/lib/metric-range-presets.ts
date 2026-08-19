import type { TimeframeUnit } from "@/lib/types";

export interface RangePreset {
  key: string;
  labelKey: string;
  relativeDays: number;
  timeframeUnit: TimeframeUnit;
  timeframeCount: number;
}

export const DEFAULT_RANGE_KEY = "30d";

/**
 * Preset ranges only — no raw timeframe-unit/count controls exposed
 * separately. `timeframeUnit` is only used to decide whether the chart's
 * x-axis shows a time-of-day (hour/minute ranges) or just a date — the
 * chart itself always plots every raw point in the range, never bucketed.
 * Shared by the metric detail page and the dashboard-element config picker so both
 * pickers stay in sync.
 */
export const RANGE_PRESETS: RangePreset[] = [
  { key: "7d", labelKey: "range7", relativeDays: 7, timeframeUnit: "hour", timeframeCount: 6 },
  { key: "30d", labelKey: "range30", relativeDays: 30, timeframeUnit: "day", timeframeCount: 1 },
  { key: "90d", labelKey: "range90", relativeDays: 90, timeframeUnit: "day", timeframeCount: 1 },
  { key: "1y", labelKey: "range1y", relativeDays: 365, timeframeUnit: "week", timeframeCount: 1 },
  { key: "3y", labelKey: "range3y", relativeDays: 1095, timeframeUnit: "month", timeframeCount: 1 },
  { key: "all", labelKey: "rangeAll", relativeDays: 36500, timeframeUnit: "month", timeframeCount: 1 },
];

export function rangePreset(key: string): RangePreset {
  return RANGE_PRESETS.find((option) => option.key === key) ?? RANGE_PRESETS[1];
}
