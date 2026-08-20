"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Pencil, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DeleteMealPlanEntryButton } from "@/components/nutrition/delete-meal-plan-entry-button";
import { MarkMealPlanEntryEatenButton } from "@/components/nutrition/mark-meal-plan-entry-eaten-button";
import { MealPlanEntryDialog } from "@/components/nutrition/meal-plan-entry-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "@/i18n/navigation";
import { mealPlanEntries } from "@/lib/api";
import { mealPlanEntriesQueryKey } from "@/lib/query-keys";
import type { MealPlanEntry } from "@/lib/types";

function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function mondayOf(dateStr: string): string {
  const d = new Date(`${dateStr}T00:00:00`);
  const dow = d.getDay();
  const diff = dow === 0 ? -6 : 1 - dow;
  d.setDate(d.getDate() + diff);
  return formatDate(d);
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setDate(d.getDate() + days);
  return formatDate(d);
}

function todayLocalDate(): string {
  return formatDate(new Date());
}

export default function MealPlanPage() {
  const t = useTranslations("mealPlan");
  const tMealType = useTranslations("mealType");
  const locale = useLocale();
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [weekStart, setWeekStart] = useState(() => mondayOf(todayLocalDate()));

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const weekEnd = addDays(weekStart, 6);
  const params = { startDate: weekStart, endDate: weekEnd };

  const { data, isLoading } = useQuery({
    queryKey: mealPlanEntriesQueryKey(params),
    queryFn: () => mealPlanEntries.list(params),
    enabled: Boolean(user),
  });

  const entriesByDate = new Map<string, MealPlanEntry[]>();
  for (const entry of data?.results ?? []) {
    const list = entriesByDate.get(entry.date) ?? [];
    list.push(entry);
    entriesByDate.set(entry.date, list);
  }

  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const dayFormatter = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short" });
  const rangeFormatter = new Intl.DateTimeFormat(locale, { day: "numeric", month: "long" });
  const today = todayLocalDate();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label={t("prevWeek")} onClick={() => setWeekStart(addDays(weekStart, -7))}>
          <ChevronLeft className="size-4" />
        </Button>
        <Button variant="outline" size="icon" aria-label={t("nextWeek")} onClick={() => setWeekStart(addDays(weekStart, 7))}>
          <ChevronRight className="size-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={() => setWeekStart(mondayOf(today))}>
          {t("today")}
        </Button>
        <span className="text-sm text-muted-foreground">
          {rangeFormatter.format(new Date(`${weekStart}T00:00:00`))} –{" "}
          {rangeFormatter.format(new Date(`${weekEnd}T00:00:00`))}
        </span>
      </div>

      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-7">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-7">
          {days.map((date) => {
            const dayEntries = entriesByDate.get(date) ?? [];
            return (
              <Card key={date} size="sm" className={date === today ? "ring-2 ring-primary" : undefined}>
                <CardHeader>
                  <CardTitle className="capitalize">
                    {dayFormatter.format(new Date(`${date}T00:00:00`))}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {dayEntries.length === 0 ? (
                    <p className="text-xs text-muted-foreground">{t("empty")}</p>
                  ) : (
                    <ul className="space-y-2">
                      {dayEntries.map((entry) => (
                        <li key={entry.id} className="space-y-1.5 rounded-md border p-2">
                          <div className="flex items-center justify-between gap-1">
                            <Badge variant="secondary" className="text-[10px]">
                              {tMealType(entry.meal_type)}
                            </Badge>
                            {entry.is_eaten && (
                              <Badge variant="outline" className="text-[10px]">
                                {t("eaten")}
                              </Badge>
                            )}
                          </div>
                          <div className="text-sm font-medium">
                            {entry.food_item_name ?? entry.recipe_name}
                          </div>
                          <div className="text-xs text-muted-foreground">{entry.calories} ккал</div>
                          <div className="flex flex-wrap items-center gap-1 pt-1">
                            {!entry.is_eaten && <MarkMealPlanEntryEatenButton entry={entry} />}
                            {!entry.is_eaten && (
                              <MealPlanEntryDialog
                                entry={entry}
                                trigger={
                                  <Button variant="ghost" size="icon" aria-label={t("editAction")}>
                                    <Pencil className="size-4" />
                                  </Button>
                                }
                              />
                            )}
                            <DeleteMealPlanEntryButton entry={entry} />
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  <MealPlanEntryDialog
                    defaultDate={date}
                    trigger={
                      <Button variant="ghost" size="sm" className="w-full justify-start text-muted-foreground">
                        <Plus className="size-4" />
                        {t("addForDay")}
                      </Button>
                    }
                  />
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
