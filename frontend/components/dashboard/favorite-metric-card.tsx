"use client";

import { Star } from "lucide-react";
import { useState } from "react";

import { ChartCard } from "@/components/dashboard/chart-card";
import { FavoriteToggleButton } from "@/components/metrics/favorite-toggle";
import { MetricChart } from "@/components/metrics/metric-chart";
import { PeriodChangeBadges } from "@/components/metrics/period-change-badges";
import { RangeSelect } from "@/components/metrics/range-select";
import { useMetricAggregate } from "@/components/metrics/use-metric-aggregate";
import { Skeleton } from "@/components/ui/skeleton";
import { DEFAULT_RANGE_KEY } from "@/lib/metric-range-presets";
import type { FavoriteMetric } from "@/lib/types";

export function FavoriteMetricCard({ favorite }: { favorite: FavoriteMetric }) {
  const [rangeKey, setRangeKey] = useState(DEFAULT_RANGE_KEY);
  // The list response already comes with a pre-bucketed default-range series
  // for every favorite in one call — only hit /aggregate/ once the user
  // actually picks a different range for this specific card.
  const isDefaultRange = rangeKey === DEFAULT_RANGE_KEY;
  const aggregateQuery = useMetricAggregate(favorite.metric_type.id, rangeKey, !isDefaultRange);

  const buckets = isDefaultRange ? favorite.buckets : aggregateQuery.data?.buckets;
  const timeframeUnit = isDefaultRange
    ? favorite.timeframe_unit
    : (aggregateQuery.data?.timeframe_unit ?? favorite.timeframe_unit);
  const loading = !isDefaultRange && aggregateQuery.isLoading;

  return (
    <ChartCard
      title={favorite.metric_type.name}
      icon={Star}
      titleExtra={<PeriodChangeBadges changes={favorite.period_changes} />}
      action={
        <div className="flex items-center gap-2">
          <RangeSelect value={rangeKey} onChange={setRangeKey} className="h-8 w-24 text-xs" />
          <FavoriteToggleButton metricType={favorite.metric_type} />
        </div>
      }
    >
      {loading || !buckets ? (
        <Skeleton className="h-80" />
      ) : (
        <MetricChart buckets={buckets} timeframeUnit={timeframeUnit} />
      )}
    </ChartCard>
  );
}
