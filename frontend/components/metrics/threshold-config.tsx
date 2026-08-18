"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, metricThresholds } from "@/lib/api";
import { METRIC_THRESHOLDS_QUERY_KEY, metricAggregatePrefixKey } from "@/lib/query-keys";
import type { MetricThreshold, MetricType } from "@/lib/types";

export function useMetricThreshold(metricTypeId: number, enabled = true): MetricThreshold | undefined {
  const { data } = useQuery({
    queryKey: METRIC_THRESHOLDS_QUERY_KEY,
    queryFn: () => metricThresholds.list(),
    enabled,
  });
  return data?.results.find((threshold) => threshold.metric_type === metricTypeId);
}

export function ThresholdConfigDialog({
  metricType,
  threshold,
}: {
  metricType: MetricType;
  threshold: MetricThreshold | undefined;
}) {
  const t = useTranslations("threshold");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [lower, setLower] = useState(threshold?.lower_bound?.toString() ?? "");
  const [upper, setUpper] = useState(threshold?.upper_bound?.toString() ?? "");

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) {
      setLower(threshold?.lower_bound?.toString() ?? "");
      setUpper(threshold?.upper_bound?.toString() ?? "");
    }
    setOpen(nextOpen);
  }

  const mutation = useMutation({
    mutationFn: () => {
      const lower_bound = lower.trim() ? Number(lower) : null;
      const upper_bound = upper.trim() ? Number(upper) : null;
      if (threshold) {
        return metricThresholds.update(threshold.id, { lower_bound, upper_bound });
      }
      return metricThresholds.create({ metric_type: metricType.id, lower_bound, upper_bound });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: METRIC_THRESHOLDS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: metricAggregatePrefixKey(metricType.id) });
      toast.success(t("saved"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("saveFailed"));
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!lower.trim() && !upper.trim()) {
      toast.error(t("needBound"));
      return;
    }
    mutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm">
            {threshold ? t("editRange") : t("setRange")}
          </Button>
        }
      />
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t("title", { name: metricType.name })}</DialogTitle>
            <DialogDescription>{t("description")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="lower-bound">
                {t("lowerBound")} {metricType.unit && `(${metricType.unit})`}
              </Label>
              <Input
                id="lower-bound"
                type="number"
                step="any"
                value={lower}
                onChange={(e) => setLower(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="upper-bound">
                {t("upperBound")} {metricType.unit && `(${metricType.unit})`}
              </Label>
              <Input
                id="upper-bound"
                type="number"
                step="any"
                value={upper}
                onChange={(e) => setUpper(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? t("saving") : t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
