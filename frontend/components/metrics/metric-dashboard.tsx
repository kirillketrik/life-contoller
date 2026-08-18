"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { FavoriteToggleButton } from "@/components/metrics/favorite-toggle";
import { MetricChart } from "@/components/metrics/metric-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { metricAggregate } from "@/lib/api";
import { metricAggregateQueryKey } from "@/lib/query-keys";
import type { MetricType, TimeframeUnit } from "@/lib/types";

/**
 * Preset ranges only — no raw bucket-unit/count controls. Bucket granularity
 * is picked per range so the chart stays readable (e.g. a 3-year range in
 * daily buckets would be ~1000 candles), not exposed as a separate choice.
 */
const RANGE_PRESETS: {
  key: string;
  labelKey: string;
  relativeDays: number;
  timeframeUnit: TimeframeUnit;
  timeframeCount: number;
}[] = [
  { key: "7d", labelKey: "range7", relativeDays: 7, timeframeUnit: "hour", timeframeCount: 6 },
  { key: "30d", labelKey: "range30", relativeDays: 30, timeframeUnit: "day", timeframeCount: 1 },
  { key: "90d", labelKey: "range90", relativeDays: 90, timeframeUnit: "day", timeframeCount: 1 },
  { key: "1y", labelKey: "range1y", relativeDays: 365, timeframeUnit: "week", timeframeCount: 1 },
  { key: "3y", labelKey: "range3y", relativeDays: 1095, timeframeUnit: "month", timeframeCount: 1 },
  { key: "all", labelKey: "rangeAll", relativeDays: 36500, timeframeUnit: "month", timeframeCount: 1 },
];

export function MetricDashboard({ metricType }: { metricType: MetricType }) {
  const t = useTranslations("metricDashboard");
  const [rangeKey, setRangeKey] = useState("30d");
  const preset = RANGE_PRESETS.find((option) => option.key === rangeKey) ?? RANGE_PRESETS[1];

  const params = {
    timeframeUnit: preset.timeframeUnit,
    timeframeCount: preset.timeframeCount,
    relativeDays: preset.relativeDays,
  };
  const { data, isLoading } = useQuery({
    queryKey: metricAggregateQueryKey(metricType.id, params),
    queryFn: () => metricAggregate.get(metricType.id, params),
  });

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-1">
          <CardTitle className="text-base">{t("title")}</CardTitle>
          <FavoriteToggleButton metricType={metricType} />
        </div>
        <Select
          items={Object.fromEntries(RANGE_PRESETS.map((option) => [option.key, t(option.labelKey)]))}
          value={rangeKey}
          onValueChange={(v) => setRangeKey(v ?? "30d")}
        >
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RANGE_PRESETS.map((option) => (
              <SelectItem key={option.key} value={option.key}>
                {t(option.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? (
          <Skeleton className="h-80" />
        ) : (
          <>
            <MetricChart buckets={data.buckets} timeframeUnit={data.timeframe_unit} />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <SummaryStat label={t("statMin")} value={data.summary.min} unit={metricType.unit} />
              <SummaryStat label={t("statMax")} value={data.summary.max} unit={metricType.unit} />
              <SummaryStat label={t("statAvg")} value={data.summary.avg} unit={metricType.unit} />
              {data.time_in_range_percent !== null && (
                <SummaryStat label={t("statTimeInRange")} value={data.time_in_range_percent} unit="%" />
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function SummaryStat({ label, value, unit }: { label: string; value: number | null; unit: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">
        {value === null ? (
          "—"
        ) : (
          <>
            {value.toFixed(1)}
            {unit && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}
          </>
        )}
      </p>
    </div>
  );
}
