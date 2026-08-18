"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { MetricChart } from "@/components/metrics/metric-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

const TIMEFRAME_UNITS: { value: TimeframeUnit; labelKey: string }[] = [
  { value: "minute", labelKey: "unitMinute" },
  { value: "hour", labelKey: "unitHour" },
  { value: "day", labelKey: "unitDay" },
  { value: "week", labelKey: "unitWeek" },
  { value: "month", labelKey: "unitMonth" },
  { value: "year", labelKey: "unitYear" },
];

const RANGE_OPTIONS: { value: number; labelKey: string }[] = [
  { value: 7, labelKey: "range7" },
  { value: 30, labelKey: "range30" },
  { value: 90, labelKey: "range90" },
  { value: 365, labelKey: "range365" },
];

export function MetricDashboard({ metricType }: { metricType: MetricType }) {
  const t = useTranslations("metricDashboard");
  const [timeframeUnit, setTimeframeUnit] = useState<TimeframeUnit>("day");
  const [timeframeCount, setTimeframeCount] = useState(1);
  const [relativeDays, setRelativeDays] = useState(30);

  const params = { timeframeUnit, timeframeCount, relativeDays };
  const { data, isLoading } = useQuery({
    queryKey: metricAggregateQueryKey(metricType.id, params),
    queryFn: () => metricAggregate.get(metricType.id, params),
  });

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="text-base">{t("title")}</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            type="number"
            min={1}
            value={timeframeCount}
            onChange={(e) => setTimeframeCount(Math.max(1, Number(e.target.value) || 1))}
            className="w-16"
            aria-label={t("timeframeCountAria")}
          />
          <Select value={timeframeUnit} onValueChange={(v) => setTimeframeUnit(v as TimeframeUnit)}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIMEFRAME_UNITS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={String(relativeDays)} onValueChange={(v) => setRelativeDays(Number(v))}>
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RANGE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={String(option.value)}>
                  {t(option.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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
