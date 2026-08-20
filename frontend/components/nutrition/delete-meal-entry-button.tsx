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
import { ApiError, mealEntries } from "@/lib/api";
import { invalidateDailyNutritionMetricQueries, MEAL_ENTRIES_QUERY_KEY } from "@/lib/query-keys";
import type { MealEntry } from "@/lib/types";

export function DeleteMealEntryButton({ entry }: { entry: MealEntry }) {
  const t = useTranslations("mealEntry");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => mealEntries.delete(entry.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MEAL_ENTRIES_QUERY_KEY });
      invalidateDailyNutritionMetricQueries(queryClient);
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
