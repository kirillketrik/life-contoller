"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ApiError, metricTypes } from "@/lib/api";
import { METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";
import { type Aggregation, createMetricTypeSchema, type ValueType } from "@/lib/types";

export function CreateMetricTypeDialog() {
  const t = useTranslations("metrics");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("");
  const [valueType, setValueType] = useState<ValueType>("number");
  const [aggregation, setAggregation] = useState<Aggregation>("");
  const [isComputed, setIsComputed] = useState(false);

  function reset() {
    setName("");
    setUnit("");
    setValueType("number");
    setAggregation("");
    setIsComputed(false);
  }

  const mutation = useMutation({
    mutationFn: metricTypes.create,
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: METRIC_TYPES_QUERY_KEY });
      toast.success(t("created", { name: created.name }));
      reset();
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("createFailed"));
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const parsed = createMetricTypeSchema.safeParse({
      name,
      unit,
      value_type: valueType,
      aggregation,
      is_computed: isComputed,
    });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? t("createFailed"));
      return;
    }
    mutation.mutate(parsed.data);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>{t("new")}</Button>} />
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t("createTitle")}</DialogTitle>
            <DialogDescription>{t("createDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="mt-name">{t("name")}</Label>
              <Input id="mt-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mt-unit">{t("unitLabel")}</Label>
              <Input
                id="mt-unit"
                placeholder={t("unitPlaceholder")}
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("valueType")}</Label>
              <Select
                items={{
                  number: t("valueTypeNumber"),
                  text: t("valueTypeText"),
                  boolean: t("valueTypeBoolean"),
                  date: t("valueTypeDate"),
                }}
                value={valueType}
                onValueChange={(v) => setValueType(v as ValueType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="number">{t("valueTypeNumber")}</SelectItem>
                  <SelectItem value="text">{t("valueTypeText")}</SelectItem>
                  <SelectItem value="boolean">{t("valueTypeBoolean")}</SelectItem>
                  <SelectItem value="date">{t("valueTypeDate")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t("aggregationLabel")}</Label>
              <Select
                items={{
                  none: t("aggregationNone"),
                  sum: t("aggregationSum"),
                  last: t("aggregationLast"),
                  avg: t("aggregationAvg"),
                }}
                value={aggregation || "none"}
                onValueChange={(v) => setAggregation(v === "none" ? "" : (v as Aggregation))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t("aggregationNone")}</SelectItem>
                  <SelectItem value="sum">{t("aggregationSum")}</SelectItem>
                  <SelectItem value="last">{t("aggregationLast")}</SelectItem>
                  <SelectItem value="avg">{t("aggregationAvg")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="mt-computed">{t("computed")}</Label>
                <p className="text-xs text-muted-foreground">{t("computedHint")}</p>
              </div>
              <Switch id="mt-computed" checked={isComputed} onCheckedChange={setIsComputed} />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? t("creating") : t("create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
