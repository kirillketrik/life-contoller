"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { use, useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { CreateMetricEntryDialog } from "@/components/metrics/create-metric-entry-dialog";
import { MetricDashboard } from "@/components/metrics/metric-dashboard";
import { ThresholdConfigDialog, useMetricThreshold } from "@/components/metrics/threshold-config";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRouter } from "@/i18n/navigation";
import { metricEntries, metricTypes } from "@/lib/api";
import { metricEntriesQueryKey, metricTypeQueryKey } from "@/lib/query-keys";
import type { MetricEntry, MetricType } from "@/lib/types";

export default function MetricTypeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const metricTypeId = Number(id);
  const t = useTranslations("metricDetail");
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const metricTypeQuery = useQuery({
    queryKey: metricTypeQueryKey(metricTypeId),
    queryFn: () => metricTypes.get(metricTypeId),
    enabled: Boolean(user),
  });

  const entriesQuery = useQuery({
    queryKey: metricEntriesQueryKey(metricTypeId),
    queryFn: () => metricEntries.list(metricTypeId),
    enabled: Boolean(user) && !metricTypeQuery.data?.is_computed,
  });

  const threshold = useMetricThreshold(metricTypeId, Boolean(user));

  function formatValue(entry: MetricEntry, metricType: MetricType | undefined): string {
    if (metricType?.value_type === "boolean") return entry.value ? t("yes") : t("no");
    if (metricType?.unit) return `${entry.value} ${metricType.unit}`;
    return String(entry.value);
  }

  if (metricTypeQuery.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const metricType = metricTypeQuery.data;
  if (!metricType) {
    return <p className="text-sm text-muted-foreground">{t("notFound")}</p>;
  }

  const chartable = metricType.is_computed || metricType.value_type === "number";
  const entries = entriesQuery.data?.results ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{metricType.name}</h1>
          <p className="text-sm text-muted-foreground">
            {metricType.value_type}
            {metricType.unit ? ` · ${metricType.unit}` : ""}
            {metricType.is_computed ? t("computedSuffix") : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {chartable && <ThresholdConfigDialog metricType={metricType} threshold={threshold} />}
          {!metricType.is_computed && <CreateMetricEntryDialog metricType={metricType} />}
        </div>
      </div>

      {chartable && <MetricDashboard metricType={metricType} />}

      {metricType.is_computed ? null : entriesQuery.isLoading ? (
        <Skeleton className="h-64" />
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("noEntries")}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("recordedAtHeader")}</TableHead>
              <TableHead>{t("valueHeader")}</TableHead>
              <TableHead>{t("noteHeader")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell>{new Date(entry.recorded_at).toLocaleString()}</TableCell>
                <TableCell>{formatValue(entry, metricType)}</TableCell>
                <TableCell className="text-muted-foreground">
                  {(entry.context?.note as string | undefined) ?? "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
