"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Gauge, ListTree, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { ChartCard } from "@/components/dashboard/chart-card";
import { HorizontalBarList } from "@/components/dashboard/horizontal-bar-list";
import { MonthlyTrendChart } from "@/components/dashboard/monthly-trend-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "@/i18n/navigation";
import { dashboardSummary } from "@/lib/api";
import { DASHBOARD_SUMMARY_QUERY_KEY } from "@/lib/query-keys";

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const { data, isLoading } = useQuery({
    queryKey: DASHBOARD_SUMMARY_QUERY_KEY,
    queryFn: () => dashboardSummary.get(),
    enabled: Boolean(user),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      <div className="grid gap-3 sm:grid-cols-3">
        <KpiCard icon={ListTree} label={t("kpiMetricTypes")} value={data?.metric_type_count} loading={isLoading} />
        <KpiCard icon={Activity} label={t("kpiEntries")} value={data?.entry_count} loading={isLoading} />
        <KpiCard icon={Gauge} label={t("kpiThresholds")} value={data?.threshold_count} loading={isLoading} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <ChartCard title={t("breakdownTitle")} icon={ListTree}>
          {isLoading ? (
            <Skeleton className="h-40" />
          ) : (
            <HorizontalBarList
              items={(data?.entries_by_metric_type ?? []).map((row) => ({
                label: row.metric_type_name,
                value: row.count,
              }))}
              emptyLabel={t("noData")}
            />
          )}
        </ChartCard>
        <ChartCard title={t("trendTitle")} icon={Activity}>
          {isLoading ? (
            <Skeleton className="h-64" />
          ) : (
            <MonthlyTrendChart data={data?.entries_by_month ?? []} emptyLabel={t("noData")} />
          )}
        </ChartCard>
      </div>
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  loading,
}: {
  icon: LucideIcon;
  label: string;
  value: number | undefined;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm font-normal text-muted-foreground">{label}</CardTitle>
        <Icon className="size-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <p className="text-2xl font-semibold tabular-nums">{value ?? 0}</p>
        )}
      </CardContent>
    </Card>
  );
}
