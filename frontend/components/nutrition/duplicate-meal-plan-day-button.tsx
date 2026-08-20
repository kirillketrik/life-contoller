"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
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
import { ApiError, mealPlanEntries } from "@/lib/api";
import { MEAL_PLAN_ENTRIES_QUERY_KEY } from "@/lib/query-keys";

/** Copies every planned meal from `date` onto a chosen target date — the
 * backend's `duplicate-day` action is purely additive (existing plans on the
 * target date are kept, not replaced), so re-running this is always safe.
 * `defaultTargetDate` seeds the date input (the week view passes "this day,
 * one week later" — the common case), and the field stays editable for any
 * other target. Disabled when the day has nothing to copy. */
export function DuplicateMealPlanDayButton({
  date,
  defaultTargetDate,
  disabled,
}: {
  date: string;
  defaultTargetDate: string;
  disabled?: boolean;
}) {
  const t = useTranslations("mealPlan");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [targetDate, setTargetDate] = useState(defaultTargetDate);

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) setTargetDate(defaultTargetDate);
    setOpen(nextOpen);
  }

  const mutation = useMutation({
    mutationFn: () =>
      mealPlanEntries.duplicateDay({ source_date: date, target_date: targetDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MEAL_PLAN_ENTRIES_QUERY_KEY });
      toast.success(t("duplicateSuccess"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("duplicateFailed"));
    },
  });

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            disabled={disabled}
            className="w-full justify-start text-muted-foreground"
          >
            <Copy className="size-4" />
            {t("duplicateDay")}
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("duplicateTitle")}</DialogTitle>
          <DialogDescription>{t("duplicateDescription")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="duplicate-target-date">{t("duplicateTargetDate")}</Label>
          <Input
            id="duplicate-target-date"
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            required
          />
        </div>
        <DialogFooter>
          <Button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? t("duplicating") : t("duplicateConfirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
