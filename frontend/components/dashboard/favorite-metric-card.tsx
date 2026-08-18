import { Star } from "lucide-react";

import { ChartCard } from "@/components/dashboard/chart-card";
import { FavoriteToggleButton } from "@/components/metrics/favorite-toggle";
import { MetricChart } from "@/components/metrics/metric-chart";
import type { FavoriteMetric } from "@/lib/types";

export function FavoriteMetricCard({ favorite }: { favorite: FavoriteMetric }) {
  return (
    <ChartCard
      title={favorite.metric_type.name}
      icon={Star}
      action={<FavoriteToggleButton metricType={favorite.metric_type} />}
    >
      <MetricChart buckets={favorite.buckets} timeframeUnit={favorite.timeframe_unit} />
    </ChartCard>
  );
}
