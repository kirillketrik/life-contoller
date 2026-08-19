"use client";

import { useTranslations } from "next-intl";

import {
  DashboardElementConfigDialog,
  useDashboardElementConfig,
} from "@/components/metrics/dashboard-element-config";
import { MetricChart } from "@/components/metrics/metric-chart";
import { RangeSelect } from "@/components/metrics/range-select";
import { SummaryStat } from "@/components/metrics/summary-stat";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AggregateResponse, MetricType } from "@/lib/types";

export function MetricDashboard({
  metricType,
  rangeKey,
  onRangeChange,
  data,
  isLoading,
}: {
  metricType: MetricType;
  rangeKey: string;
  onRangeChange: (rangeKey: string) => void;
  data: AggregateResponse | undefined;
  isLoading: boolean;
}) {
  const t = useTranslations("metricDashboard");
  const elementConfig = useDashboardElementConfig(metricType.id);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">{t("title")}</CardTitle>
          <DashboardElementConfigDialog metricType={metricType} config={elementConfig} />
        </div>
        <RangeSelect value={rangeKey} onChange={onRangeChange} />
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? (
          <Skeleton className="h-80" />
        ) : (
          <>
            <MetricChart buckets={data.buckets} timeframeUnit={data.timeframe_unit} />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <SummaryStat label={t("statCurrent")} value={data.current} unit={metricType.unit} />
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
