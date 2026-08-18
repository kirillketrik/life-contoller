"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
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

interface ChoiceOptionRow {
  code: string;
  label: string;
  numericValue: string;
}

function emptyOptionRow(): ChoiceOptionRow {
  return { code: "", label: "", numericValue: "" };
}

export function CreateMetricTypeDialog() {
  const t = useTranslations("metrics");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("");
  const [valueType, setValueType] = useState<ValueType>("number");
  const [aggregation, setAggregation] = useState<Aggregation>("");
  const [isComputed, setIsComputed] = useState(false);
  const [isSingleton, setIsSingleton] = useState(false);
  const [options, setOptions] = useState<ChoiceOptionRow[]>([emptyOptionRow()]);

  function reset() {
    setName("");
    setUnit("");
    setValueType("number");
    setAggregation("");
    setIsComputed(false);
    setIsSingleton(false);
    setOptions([emptyOptionRow()]);
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

  function updateOption(index: number, patch: Partial<ChoiceOptionRow>) {
    setOptions((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addOption() {
    setOptions((prev) => [...prev, emptyOptionRow()]);
  }

  function removeOption(index: number) {
    setOptions((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== index) : prev));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const choices =
      valueType === "choice"
        ? options
            .filter((row) => row.code.trim() && row.label.trim())
            .map((row, index) => ({
              code: row.code.trim(),
              label: row.label.trim(),
              numeric_value: row.numericValue.trim() ? Number(row.numericValue) : null,
              order: index,
            }))
        : undefined;
    const parsed = createMetricTypeSchema.safeParse({
      name,
      unit,
      value_type: valueType,
      aggregation,
      is_computed: isComputed,
      is_singleton: isSingleton,
      choices,
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
                  choice: t("valueTypeChoice"),
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
                  <SelectItem value="choice">{t("valueTypeChoice")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {valueType === "choice" && (
              <div className="space-y-2">
                <Label>{t("choiceOptions")}</Label>
                <div className="space-y-2">
                  {options.map((row, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <Input
                        placeholder={t("choiceCodePlaceholder")}
                        value={row.code}
                        onChange={(e) => updateOption(index, { code: e.target.value })}
                        className="w-28"
                      />
                      <Input
                        placeholder={t("choiceLabelPlaceholder")}
                        value={row.label}
                        onChange={(e) => updateOption(index, { label: e.target.value })}
                      />
                      <Input
                        type="number"
                        step="any"
                        placeholder={t("choiceNumericPlaceholder")}
                        value={row.numericValue}
                        onChange={(e) => updateOption(index, { numericValue: e.target.value })}
                        className="w-24"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => removeOption(index)}
                        disabled={options.length === 1}
                        aria-label={t("removeOption")}
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  ))}
                </div>
                <Button type="button" variant="outline" size="sm" onClick={addOption}>
                  <Plus className="size-4" />
                  {t("addOption")}
                </Button>
              </div>
            )}
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
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="mt-singleton">{t("singleton")}</Label>
                <p className="text-xs text-muted-foreground">{t("singletonHint")}</p>
              </div>
              <Switch id="mt-singleton" checked={isSingleton} onCheckedChange={setIsSingleton} />
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
