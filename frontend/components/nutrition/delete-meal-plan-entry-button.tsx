"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
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
import { ApiError, mealPlanEntries } from "@/lib/api";
import { MEAL_PLAN_ENTRIES_QUERY_KEY } from "@/lib/query-keys";
import type { MealPlanEntry } from "@/lib/types";

/** Deletes only the plan row — never the resulting `MealEntry` a marked-
 * eaten plan may have produced (they're decoupled once created, see
 * MealPlanEntry.resulting_meal_entry's SET_NULL note in CLAUDE.md), so this
 * stays safe to offer even after a plan has been marked eaten. */
export function DeleteMealPlanEntryButton({ entry }: { entry: MealPlanEntry }) {
  const t = useTranslations("mealPlanEntry");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => mealPlanEntries.delete(entry.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MEAL_PLAN_ENTRIES_QUERY_KEY });
      toast.success(t("deleted"));
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("deleteFailed"));
    },
  });

  return (
    <AlertDialog>
      <AlertDialogTrigger
        render={
          <Button variant="ghost" size="icon" aria-label={t("delete")}>
            <Trash2 className="size-4" />
          </Button>
        }
      />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("deleteConfirmTitle")}</AlertDialogTitle>
          <AlertDialogDescription>{t("deleteConfirmDescription")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("deleteCancel")}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? t("deleting") : t("deleteConfirmAction")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
