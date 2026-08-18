"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { type ReactElement, useState } from "react";
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
import { ApiError, metricEntries } from "@/lib/api";
import { metricAggregatePrefixKey, metricEntriesQueryKey } from "@/lib/query-keys";
import {
  type CreateMetricEntryInput,
  createMetricEntrySchema,
  type MetricEntry,
  type MetricType,
} from "@/lib/types";

function toLocalInputValue(date: Date): string {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function initialValues(metricType: MetricType, entry: MetricEntry | undefined) {
  return {
    numberValue: entry && metricType.value_type === "number" ? String(entry.value) : "",
    textValue: entry && metricType.value_type === "text" ? String(entry.value) : "",
    booleanValue: entry && metricType.value_type === "boolean" ? Boolean(entry.value) : false,
    dateValue: entry && metricType.value_type === "date" ? String(entry.value) : "",
    choiceValue: entry && metricType.value_type === "choice" ? String(entry.value) : "",
    note: (entry?.context?.note as string | undefined) ?? "",
    recordedAt: entry ? toLocalInputValue(new Date(entry.recorded_at)) : toLocalInputValue(new Date()),
  };
}

/** Logs a new value for a metric type, or edits an existing entry when
 * `entry` is passed — the same value-type-branching form either way, since
 * the only difference is which mutation submit calls. Pass `trigger` to
 * override the default open button (e.g. a small icon button in a table
 * row); otherwise renders the default "log value" / "edit value" button. */
export function MetricEntryDialog({
  metricType,
  entry,
  trigger,
}: {
  metricType: MetricType;
  entry?: MetricEntry;
  trigger?: ReactElement;
}) {
  const t = useTranslations("metricEntry");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(() => initialValues(metricType, entry));

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) setValues(initialValues(metricType, entry));
    setOpen(nextOpen);
  }

  const mutation = useMutation({
    mutationFn: (data: CreateMetricEntryInput) =>
      entry ? metricEntries.update(entry.id, data) : metricEntries.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: metricEntriesQueryKey(metricType.id) });
      queryClient.invalidateQueries({ queryKey: metricAggregatePrefixKey(metricType.id) });
      toast.success(entry ? t("updated") : t("logged"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : entry ? t("updateFailed") : t("logFailed"));
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (metricType.value_type === "choice" && !values.choiceValue) {
      toast.error(t("choiceRequired"));
      return;
    }
    const value =
      metricType.value_type === "number"
        ? Number(values.numberValue)
        : metricType.value_type === "boolean"
          ? values.booleanValue
          : metricType.value_type === "date"
            ? values.dateValue
            : metricType.value_type === "choice"
              ? values.choiceValue
              : values.textValue;
    const parsed = createMetricEntrySchema.safeParse({
      metric_type: metricType.id,
      value,
      context: values.note ? { note: values.note } : null,
      recorded_at: new Date(values.recordedAt).toISOString(),
    });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? t("invalid"));
      return;
    }
    mutation.mutate(parsed.data);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={trigger ?? <Button>{entry ? t("editTrigger") : t("trigger")}</Button>} />
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {entry ? t("editTitle", { name: metricType.name }) : t("logTitle", { name: metricType.name })}
            </DialogTitle>
            <DialogDescription>{entry ? t("editDescription") : t("logDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            {metricType.value_type === "number" && (
              <div className="space-y-2">
                <Label htmlFor="value">
                  {t("value")} {metricType.unit && `(${metricType.unit})`}
                </Label>
                <Input
                  id="value"
                  type="number"
                  step="any"
                  value={values.numberValue}
                  onChange={(e) => setValues((v) => ({ ...v, numberValue: e.target.value }))}
                  required
                />
              </div>
            )}
            {metricType.value_type === "text" && (
              <div className="space-y-2">
                <Label htmlFor="value">{t("value")}</Label>
                <Input
                  id="value"
                  value={values.textValue}
                  onChange={(e) => setValues((v) => ({ ...v, textValue: e.target.value }))}
                  required
                />
              </div>
            )}
            {metricType.value_type === "boolean" && (
              <div className="flex items-center justify-between">
                <Label htmlFor="value">{t("value")}</Label>
                <Switch
                  id="value"
                  checked={values.booleanValue}
                  onCheckedChange={(checked) => setValues((v) => ({ ...v, booleanValue: checked }))}
                />
              </div>
            )}
            {metricType.value_type === "date" && (
              <div className="space-y-2">
                <Label htmlFor="value">{t("value")}</Label>
                <Input
                  id="value"
                  type="date"
                  value={values.dateValue}
                  onChange={(e) => setValues((v) => ({ ...v, dateValue: e.target.value }))}
                  required
                />
              </div>
            )}
            {metricType.value_type === "choice" && (
              <div className="space-y-2">
                <Label>{t("value")}</Label>
                <Select
                  items={Object.fromEntries(metricType.choices.map((c) => [c.code, c.label]))}
                  value={values.choiceValue}
                  onValueChange={(v) => setValues((prev) => ({ ...prev, choiceValue: v ?? "" }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t("choicePlaceholder")} />
                  </SelectTrigger>
                  <SelectContent>
                    {metricType.choices.map((choice) => (
                      <SelectItem key={choice.code} value={choice.code}>
                        {choice.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="recorded-at">{t("recordedAt")}</Label>
              <Input
                id="recorded-at"
                type="datetime-local"
                value={values.recordedAt}
                onChange={(e) => setValues((v) => ({ ...v, recordedAt: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="note">{t("note")}</Label>
              <Input
                id="note"
                value={values.note}
                onChange={(e) => setValues((v) => ({ ...v, note: e.target.value }))}
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
