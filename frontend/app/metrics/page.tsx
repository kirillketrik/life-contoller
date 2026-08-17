"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";
import { CreateMetricTypeDialog } from "@/components/metrics/create-metric-type-dialog";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { metricTypes } from "@/lib/api";
import { METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";

export default function MetricsPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const { data, isLoading } = useQuery({
    queryKey: METRIC_TYPES_QUERY_KEY,
    queryFn: () => metricTypes.list(),
    enabled: Boolean(user),
  });

  const types = data?.results ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Metric types</h1>
          <p className="text-sm text-muted-foreground">
            Definitions of what can be logged. {user?.is_admin ? "" : "Only admins can create or edit these."}
          </p>
        </div>
        {user?.is_admin && <CreateMetricTypeDialog />}
      </div>

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : types.length === 0 ? (
        <p className="text-sm text-muted-foreground">No metric types yet.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {types.map((type) => (
            <Link key={type.id} href={`/metrics/${type.id}`}>
              <Card className="h-full transition-colors hover:bg-accent/50">
                <CardHeader>
                  <CardTitle className="flex items-center justify-between text-base">
                    {type.name}
                    <Badge variant="outline">{type.value_type}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  {type.unit ? `Unit: ${type.unit}` : "No unit"}
                  {type.aggregation ? ` · Aggregation: ${type.aggregation}` : ""}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
