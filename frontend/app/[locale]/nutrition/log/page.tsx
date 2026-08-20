"use client";

import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { SummaryStat } from "@/components/metrics/summary-stat";
import { DeleteMealEntryButton } from "@/components/nutrition/delete-meal-entry-button";
import { MealEntryDialog } from "@/components/nutrition/meal-entry-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRouter } from "@/i18n/navigation";
import { mealEntries } from "@/lib/api";
import { mealEntriesQueryKey } from "@/lib/query-keys";

function todayLocalDate(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  return new Date(now.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

export default function NutritionLogPage() {
  const t = useTranslations("nutritionLog");
  const tMealType = useTranslations("mealType");
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [date, setDate] = useState(() => todayLocalDate());

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const { data, isLoading } = useQuery({
    queryKey: mealEntriesQueryKey(date),
    queryFn: () => mealEntries.list(date),
    enabled: Boolean(user),
  });

  const entries = data?.results ?? [];
  const totals = entries.reduce(
    (acc, entry) => ({
      calories: acc.calories + entry.calories,
      protein: acc.protein + entry.protein,
      fat: acc.fat + entry.fat,
      carbs: acc.carbs + entry.carbs,
    }),
    { calories: 0, protein: 0, fat: 0, carbs: 0 },
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <MealEntryDialog defaultDate={date} />
      </div>

      <Input
        type="date"
        value={date}
        onChange={(e) => setDate(e.target.value)}
        className="max-w-xs"
      />

      <div className="grid gap-3 sm:grid-cols-4">
        <SummaryStat label={t("statCalories")} value={totals.calories} unit="ккал" />
        <SummaryStat label={t("statProtein")} value={totals.protein} unit="г" />
        <SummaryStat label={t("statFat")} value={totals.fat} unit="г" />
        <SummaryStat label={t("statCarbs")} value={totals.carbs} unit="г" />
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("empty")}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("mealTypeHeader")}</TableHead>
              <TableHead>{t("foodItemHeader")}</TableHead>
              <TableHead className="text-right">{t("quantityHeader")}</TableHead>
              <TableHead className="text-right">{t("caloriesHeader")}</TableHead>
              <TableHead className="text-right">{t("actionsHeader")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell>{tMealType(entry.meal_type)}</TableCell>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    {entry.food_item_name ?? entry.recipe_name}
                    {entry.recipe_name && <Badge variant="outline">{t("recipeBadge")}</Badge>}
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  {entry.food_item_name ? `${entry.quantity_g} г` : `× ${entry.servings}`}
                </TableCell>
                <TableCell className="text-right">{entry.calories}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <MealEntryDialog
                      entry={entry}
                      trigger={
                        <Button variant="ghost" size="icon" aria-label={t("editAction")}>
                          <Pencil className="size-4" />
                        </Button>
                      }
                    />
                    <DeleteMealEntryButton entry={entry} />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
