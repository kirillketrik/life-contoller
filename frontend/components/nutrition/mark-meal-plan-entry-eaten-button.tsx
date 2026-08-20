"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError, mealPlanEntries } from "@/lib/api";
import {
  invalidateDailyNutritionMetricQueries,
  MEAL_ENTRIES_QUERY_KEY,
  MEAL_PLAN_ENTRIES_QUERY_KEY,
} from "@/lib/query-keys";
import type { MealPlanEntry } from "@/lib/types";

/** Converts a planned meal into a real logged `MealEntry` via
 * `services.mark_meal_plan_entry_eaten` — invalidates both the plan list
 * (to flip this entry's `is_eaten`), the meal-entries list (the food diary
 * now has a new row for whatever date this plan was for), and the
 * materialized daily-total metric queries the new MealEntry recomputes. */
export function MarkMealPlanEntryEatenButton({ entry }: { entry: MealPlanEntry }) {
  const t = useTranslations("mealPlan");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => mealPlanEntries.markEaten(entry.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MEAL_PLAN_ENTRIES_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: MEAL_ENTRIES_QUERY_KEY });
      invalidateDailyNutritionMetricQueries(queryClient);
      toast.success(t("markEatenSuccess"));
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : t("markEatenFailed"));
    },
  });

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      <Check className="size-4" />
      {mutation.isPending ? t("markingEaten") : t("markEaten")}
    </Button>
  );
}
