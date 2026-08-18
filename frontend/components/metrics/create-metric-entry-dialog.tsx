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
import { ApiError, metricEntries } from "@/lib/api";
import { metricAggregatePrefixKey, metricEntriesQueryKey } from "@/lib/query-keys";
import { createMetricEntrySchema, type MetricType } from "@/lib/types";

function toLocalInputValue(date: Date): string {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

export function CreateMetricEntryDialog({ metricType }: { metricType: MetricType }) {
  const t = useTranslations("metricEntry");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [numberValue, setNumberValue] = useState("");
  const [textValue, setTextValue] = useState("");
  const [booleanValue, setBooleanValue] = useState(false);
  const [dateValue, setDateValue] = useState("");
  const [choiceValue, setChoiceValue] = useState("");
  const [note, setNote] = useState("");
  const [recordedAt, setRecordedAt] = useState(() => toLocalInputValue(new Date()));

  function reset() {
    setNumberValue("");
    setTextValue("");
    setBooleanValue(false);
    setDateValue("");
    setChoiceValue("");
    setNote("");
    setRecordedAt(toLocalInputValue(new Date()));
  }

  const mutation = useMutation({
    mutationFn: metricEntries.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: metricEntriesQueryKey(metricType.id) });
      queryClient.invalidateQueries({ queryKey: metricAggregatePrefixKey(metricType.id) });
      toast.success(t("logged"));
      reset();
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("logFailed"));
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (metricType.value_type === "choice" && !choiceValue) {
      toast.error(t("choiceRequired"));
      return;
    }
    const value =
      metricType.value_type === "number"
        ? Number(numberValue)
        : metricType.value_type === "boolean"
          ? booleanValue
          : metricType.value_type === "date"
            ? dateValue
            : metricType.value_type === "choice"
              ? choiceValue
              : textValue;
    const parsed = createMetricEntrySchema.safeParse({
      metric_type: metricType.id,
      value,
      context: note ? { note } : null,
      recorded_at: new Date(recordedAt).toISOString(),
    });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? t("invalid"));
      return;
    }
    mutation.mutate(parsed.data);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>{t("trigger")}</Button>} />
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t("logTitle", { name: metricType.name })}</DialogTitle>
            <DialogDescription>{t("logDescription")}</DialogDescription>
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
                  value={numberValue}
                  onChange={(e) => setNumberValue(e.target.value)}
                  required
                />
              </div>
            )}
            {metricType.value_type === "text" && (
              <div className="space-y-2">
                <Label htmlFor="value">{t("value")}</Label>
                <Input
                  id="value"
                  value={textValue}
                  onChange={(e) => setTextValue(e.target.value)}
                  required
                />
              </div>
            )}
            {metricType.value_type === "boolean" && (
              <div className="flex items-center justify-between">
                <Label htmlFor="value">{t("value")}</Label>
                <Switch id="value" checked={booleanValue} onCheckedChange={setBooleanValue} />
              </div>
            )}
            {metricType.value_type === "date" && (
              <div className="space-y-2">
                <Label htmlFor="value">{t("value")}</Label>
                <Input
                  id="value"
                  type="date"
                  value={dateValue}
                  onChange={(e) => setDateValue(e.target.value)}
                  required
                />
              </div>
            )}
            {metricType.value_type === "choice" && (
              <div className="space-y-2">
                <Label>{t("value")}</Label>
                <Select
                  items={Object.fromEntries(metricType.choices.map((c) => [c.code, c.label]))}
                  value={choiceValue}
                  onValueChange={(v) => setChoiceValue(v ?? "")}
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
                value={recordedAt}
                onChange={(e) => setRecordedAt(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="note">{t("note")}</Label>
              <Input id="note" value={note} onChange={(e) => setNote(e.target.value)} />
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
