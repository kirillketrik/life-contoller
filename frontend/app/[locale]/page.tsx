"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Gauge, ListTree, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { ChartCard } from "@/components/dashboard/chart-card";
import { FavoriteMetricCard } from "@/components/dashboard/favorite-metric-card";
import { HorizontalBarList } from "@/components/dashboard/horizontal-bar-list";
import { MonthlyTrendChart } from "@/components/dashboard/monthly-trend-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "@/i18n/navigation";
import { dashboardSummary, favoriteMetrics } from "@/lib/api";
import { DASHBOARD_SUMMARY_QUERY_KEY, FAVORITE_METRICS_QUERY_KEY } from "@/lib/query-keys";

const FAVORITES_DASHBOARD_LIMIT = 8;

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

  const favoritesQuery = useQuery({
    queryKey: FAVORITE_METRICS_QUERY_KEY,
    queryFn: () => favoriteMetrics.list(),
    enabled: Boolean(user),
  });
  const favorites = favoritesQuery.data ?? [];
  const visibleFavorites = favorites.slice(0, FAVORITES_DASHBOARD_LIMIT);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      <div className="grid gap-3 sm:grid-cols-3">
        <KpiCard icon={ListTree} label={t("kpiMetricTypes")} value={data?.metric_type_count} loading={isLoading} />
        <KpiCard icon={Activity} label={t("kpiEntries")} value={data?.entry_count} loading={isLoading} />
        <KpiCard icon={Gauge} label={t("kpiThresholds")} value={data?.threshold_count} loading={isLoading} />
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">{t("favoritesTitle")}</h2>
        {favoritesQuery.isLoading ? (
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            <Skeleton className="h-64" />
            <Skeleton className="h-64" />
          </div>
        ) : visibleFavorites.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("favoritesEmpty")}</p>
        ) : (
          <>
            <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {visibleFavorites.map((favorite) => (
                <FavoriteMetricCard key={favorite.id} favorite={favorite} />
              ))}
            </div>
            {favorites.length > FAVORITES_DASHBOARD_LIMIT && (
              <p className="text-sm text-muted-foreground">
                {t("favoritesMore", { shown: visibleFavorites.length, total: favorites.length })}
              </p>
            )}
          </>
        )}
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
