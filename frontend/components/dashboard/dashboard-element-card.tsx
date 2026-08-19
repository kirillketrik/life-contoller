"use client";

import { LayoutDashboard, Settings2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { ChartCard } from "@/components/dashboard/chart-card";
import { MetricChart } from "@/components/metrics/metric-chart";
import { PeriodChangeBadges } from "@/components/metrics/period-change-badges";
import { SummaryStat } from "@/components/metrics/summary-stat";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import type { DashboardElement } from "@/lib/types";

/** One dashboard block for a configured metric — chart (if enabled) plus a
 * stats row underneath showing only the enabled among current/max/min/avg.
 * No inline timeframe control here: the timeframe is configured on the
 * metric's own detail page (`DashboardElementConfigDialog`) and persisted,
 * not picked live from the dashboard. */
export function DashboardElementCard({ element }: { element: DashboardElement }) {
  const t = useTranslations("metricDashboard");
  const hasStats = element.show_current || element.show_max || element.show_min || element.show_avg;

  return (
    <ChartCard
      title={element.metric_type.name}
      icon={LayoutDashboard}
      titleExtra={<PeriodChangeBadges changes={element.period_changes} />}
      action={
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t("configureLink")}
          nativeButton={false}
          render={<Link href={`/metrics/${element.metric_type.id}`} />}
        >
          <Settings2 className="size-4" />
        </Button>
      }
    >
      <div className="space-y-4">
        {element.show_chart && (
          <MetricChart buckets={element.buckets} timeframeUnit={element.timeframe_unit ?? "day"} />
        )}
        {hasStats && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {element.show_current && (
              <SummaryStat label={t("statCurrent")} value={element.current} unit={element.metric_type.unit} />
            )}
            {element.show_max && (
              <SummaryStat label={t("statMax")} value={element.max} unit={element.metric_type.unit} />
            )}
            {element.show_min && (
              <SummaryStat label={t("statMin")} value={element.min} unit={element.metric_type.unit} />
            )}
            {element.show_avg && (
              <SummaryStat label={t("statAvg")} value={element.avg} unit={element.metric_type.unit} />
            )}
          </div>
        )}
      </div>
    </ChartCard>
  );
}
