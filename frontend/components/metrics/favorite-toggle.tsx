"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError, favoriteMetrics } from "@/lib/api";
import { FAVORITE_METRICS_QUERY_KEY } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import type { MetricType } from "@/lib/types";

export function useIsFavoriteMetric(metricTypeId: number, enabled = true): boolean {
  const { data } = useQuery({
    queryKey: FAVORITE_METRICS_QUERY_KEY,
    queryFn: () => favoriteMetrics.list(),
    enabled,
  });
  return data?.some((favorite) => favorite.metric_type.id === metricTypeId) ?? false;
}

export function FavoriteToggleButton({ metricType }: { metricType: MetricType }) {
  const t = useTranslations("favorites");
  const queryClient = useQueryClient();
  const isFavorite = useIsFavoriteMetric(metricType.id);
  const [optimistic, setOptimistic] = useState<boolean | null>(null);
  const displayedFavorite = optimistic ?? isFavorite;

  const mutation = useMutation({
    mutationFn: (next: boolean) =>
      next ? favoriteMetrics.add(metricType.id) : favoriteMetrics.remove(metricType.id),
    onMutate: (next) => setOptimistic(next),
    onError: (error) => {
      setOptimistic(null);
      toast.error(error instanceof ApiError ? error.message : t("toggleFailed"));
    },
    onSettled: () => {
      setOptimistic(null);
      queryClient.invalidateQueries({ queryKey: FAVORITE_METRICS_QUERY_KEY });
    },
  });

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      disabled={mutation.isPending}
      aria-label={displayedFavorite ? t("remove") : t("add")}
      onClick={() => mutation.mutate(!displayedFavorite)}
    >
      <Star className={cn(displayedFavorite && "fill-primary text-primary")} />
    </Button>
  );
}
