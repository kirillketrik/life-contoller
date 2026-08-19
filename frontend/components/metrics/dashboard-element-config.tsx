"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ApiError, dashboardElements } from "@/lib/api";
import { RANGE_PRESETS } from "@/lib/metric-range-presets";
import { DASHBOARD_ELEMENTS_QUERY_KEY } from "@/lib/query-keys";
import {
  dashboardElementInputSchema,
  type DashboardElement,
  type DashboardElementInput,
  type MetricType,
} from "@/lib/types";

const TIMEFRAME_OPTIONS = [...RANGE_PRESETS.map((p) => ({ key: p.key, labelKey: p.labelKey })), {
  key: "custom",
  labelKey: "rangeCustom",
}];

export function useDashboardElementConfig(
  metricTypeId: number,
  enabled = true,
): DashboardElement | undefined {
  const { data } = useQuery({
    queryKey: DASHBOARD_ELEMENTS_QUERY_KEY,
    queryFn: () => dashboardElements.list(),
    enabled,
  });
  return data?.find((element) => element.metric_type.id === metricTypeId);
}

export function DashboardElementConfigDialog({
  metricType,
  config,
}: {
  metricType: MetricType;
  config: DashboardElement | undefined;
}) {
  const t = useTranslations("dashboardElement");
  const tRange = useTranslations("metricDashboard");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const [showChart, setShowChart] = useState(config?.show_chart ?? false);
  const [showCurrent, setShowCurrent] = useState(config?.show_current ?? false);
  const [showMax, setShowMax] = useState(config?.show_max ?? false);
  const [showMin, setShowMin] = useState(config?.show_min ?? false);
  const [showAvg, setShowAvg] = useState(config?.show_avg ?? false);
  const [showTimeInRange, setShowTimeInRange] = useState(config?.show_time_in_range ?? false);
  const [timeframe, setTimeframe] = useState<string>(config?.timeframe ?? "30d");
  const [customStart, setCustomStart] = useState(config?.custom_range_start ?? "");
  const [customEnd, setCustomEnd] = useState(config?.custom_range_end ?? "");

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) {
      setShowChart(config?.show_chart ?? false);
      setShowCurrent(config?.show_current ?? false);
      setShowMax(config?.show_max ?? false);
      setShowMin(config?.show_min ?? false);
      setShowAvg(config?.show_avg ?? false);
      setShowTimeInRange(config?.show_time_in_range ?? false);
      setTimeframe(config?.timeframe ?? "30d");
      setCustomStart(config?.custom_range_start ?? "");
      setCustomEnd(config?.custom_range_end ?? "");
    }
    setOpen(nextOpen);
  }

  const saveMutation = useMutation({
    mutationFn: (data: DashboardElementInput) => dashboardElements.save(metricType.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DASHBOARD_ELEMENTS_QUERY_KEY });
      toast.success(t("saved"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("saveFailed"));
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => dashboardElements.remove(metricType.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DASHBOARD_ELEMENTS_QUERY_KEY });
      toast.success(t("removed"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("removeFailed"));
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const parsed = dashboardElementInputSchema.safeParse({
      show_chart: showChart,
      show_current: showCurrent,
      show_max: showMax,
      show_min: showMin,
      show_avg: showAvg,
      show_time_in_range: showTimeInRange,
      timeframe,
      custom_range_start: timeframe === "custom" && customStart ? customStart : null,
      custom_range_end: timeframe === "custom" && customEnd ? customEnd : null,
    });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? t("saveFailed"));
      return;
    }
    saveMutation.mutate(parsed.data);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm">
            <Settings2 className="size-4" />
            {t("configure")}
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
            <ElementToggle id="de-chart" label={t("elementChart")} checked={showChart} onCheckedChange={setShowChart} />
            <ElementToggle
              id="de-current"
              label={t("elementCurrent")}
              checked={showCurrent}
              onCheckedChange={setShowCurrent}
            />
            <ElementToggle id="de-max" label={t("elementMax")} checked={showMax} onCheckedChange={setShowMax} />
            <ElementToggle id="de-min" label={t("elementMin")} checked={showMin} onCheckedChange={setShowMin} />
            <ElementToggle id="de-avg" label={t("elementAvg")} checked={showAvg} onCheckedChange={setShowAvg} />
            <ElementToggle
              id="de-time-in-range"
              label={t("elementTimeInRange")}
              checked={showTimeInRange}
              onCheckedChange={setShowTimeInRange}
            />

            <div className="space-y-2">
              <Label htmlFor="de-timeframe">{t("timeframeLabel")}</Label>
              <Select
                items={Object.fromEntries(TIMEFRAME_OPTIONS.map((o) => [o.key, tRange(o.labelKey)]))}
                value={timeframe}
                onValueChange={(v) => setTimeframe(v ?? "30d")}
              >
                <SelectTrigger id="de-timeframe" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEFRAME_OPTIONS.map((option) => (
                    <SelectItem key={option.key} value={option.key}>
                      {tRange(option.labelKey)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {timeframe === "custom" && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="de-custom-start">{t("customRangeStart")}</Label>
                  <Input
                    id="de-custom-start"
                    type="date"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="de-custom-end">{t("customRangeEnd")}</Label>
                  <Input
                    id="de-custom-end"
                    type="date"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>
          <DialogFooter className="flex items-center sm:justify-between">
            {config && (
              <AlertDialog>
                <AlertDialogTrigger
                  render={
                    <Button type="button" variant="ghost" disabled={removeMutation.isPending}>
                      {t("remove")}
                    </Button>
                  }
                />
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t("removeConfirmTitle")}</AlertDialogTitle>
                    <AlertDialogDescription>{t("removeConfirmDescription")}</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t("removeCancel")}</AlertDialogCancel>
                    <AlertDialogAction
                      variant="destructive"
                      disabled={removeMutation.isPending}
                      onClick={() => removeMutation.mutate()}
                    >
                      {removeMutation.isPending ? t("removing") : t("removeConfirmAction")}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
            <Button type="submit" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? t("saving") : t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ElementToggle({
  id,
  label,
  checked,
  onCheckedChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <Label htmlFor={id}>{label}</Label>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
