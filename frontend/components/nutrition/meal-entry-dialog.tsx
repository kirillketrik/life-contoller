"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { ApiError, foodItems, mealEntries } from "@/lib/api";
import { FOOD_ITEMS_QUERY_KEY, MEAL_ENTRIES_QUERY_KEY } from "@/lib/query-keys";
import {
  type CreateMealEntryInput,
  createMealEntrySchema,
  type MealEntry,
  type MealType,
} from "@/lib/types";

const MEAL_TYPES: MealType[] = ["breakfast", "lunch", "dinner", "snack"];

function toLocalInputValue(date: Date): string {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function initialValues(entry: MealEntry | undefined, defaultDate: string | undefined) {
  const defaultDatetime = defaultDate ? new Date(`${defaultDate}T12:00:00`) : new Date();
  return {
    datetime: entry ? toLocalInputValue(new Date(entry.datetime)) : toLocalInputValue(defaultDatetime),
    mealType: (entry?.meal_type ?? "breakfast") as MealType,
    foodItemId: entry ? String(entry.food_item) : "",
    quantityG: entry ? String(entry.quantity_g) : "",
    cost: entry?.cost != null ? String(entry.cost) : "",
  };
}

function parseDecimal(raw: string): number {
  return Number(raw.replace(",", "."));
}

/** Logs a new meal, or edits an existing entry when `entry` is passed — same
 * value-branching-by-presence-of-prop pattern as MetricEntryDialog/
 * FoodItemDialog. `defaultDate` seeds the datetime when creating from a
 * specific day (the food diary's selected date, not necessarily today). */
export function MealEntryDialog({
  entry,
  defaultDate,
  trigger,
}: {
  entry?: MealEntry;
  defaultDate?: string;
  trigger?: ReactElement;
}) {
  const t = useTranslations("mealEntry");
  const tMealType = useTranslations("mealType");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(() => initialValues(entry, defaultDate));

  const { data: foodItemsData } = useQuery({
    queryKey: FOOD_ITEMS_QUERY_KEY,
    queryFn: () => foodItems.list(),
    enabled: open,
  });
  const availableFoodItems = foodItemsData?.results ?? [];

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) setValues(initialValues(entry, defaultDate));
    setOpen(nextOpen);
  }

  const mutation = useMutation({
    mutationFn: (data: CreateMealEntryInput) =>
      entry ? mealEntries.update(entry.id, data) : mealEntries.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MEAL_ENTRIES_QUERY_KEY });
      toast.success(entry ? t("updated") : t("logged"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : entry ? t("updateFailed") : t("logFailed"));
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!values.foodItemId) {
      toast.error(t("foodItemRequired"));
      return;
    }
    const parsed = createMealEntrySchema.safeParse({
      datetime: new Date(values.datetime).toISOString(),
      meal_type: values.mealType,
      food_item: Number(values.foodItemId),
      quantity_g: parseDecimal(values.quantityG),
      cost: values.cost.trim() ? parseDecimal(values.cost) : null,
    });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? t("invalid"));
      return;
    }
    mutation.mutate(parsed.data);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={trigger ?? <Button>{t("trigger")}</Button>} />
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{entry ? t("editTitle") : t("logTitle")}</DialogTitle>
            <DialogDescription>{entry ? t("editDescription") : t("logDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>{t("foodItem")}</Label>
              <Select
                items={Object.fromEntries(
                  availableFoodItems.map((item) => [
                    String(item.id),
                    item.brand ? `${item.name} (${item.brand})` : item.name,
                  ]),
                )}
                value={values.foodItemId}
                onValueChange={(v) => setValues((prev) => ({ ...prev, foodItemId: v ?? "" }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("foodItemPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {availableFoodItems.map((item) => (
                    <SelectItem key={item.id} value={String(item.id)}>
                      {item.brand ? `${item.name} (${item.brand})` : item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t("mealType")}</Label>
              <Select
                items={Object.fromEntries(MEAL_TYPES.map((mt) => [mt, tMealType(mt)]))}
                value={values.mealType}
                onValueChange={(v) => setValues((prev) => ({ ...prev, mealType: (v ?? "breakfast") as MealType }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MEAL_TYPES.map((mt) => (
                    <SelectItem key={mt} value={mt}>
                      {tMealType(mt)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="me-quantity">{t("quantity")}</Label>
              <Input
                id="me-quantity"
                type="text"
                inputMode="decimal"
                pattern="[0-9]*[.,]?[0-9]*"
                value={values.quantityG}
                onChange={(e) => setValues((v) => ({ ...v, quantityG: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="me-datetime">{t("datetime")}</Label>
              <Input
                id="me-datetime"
                type="datetime-local"
                value={values.datetime}
                onChange={(e) => setValues((v) => ({ ...v, datetime: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="me-cost">{t("cost")}</Label>
              <Input
                id="me-cost"
                type="text"
                inputMode="decimal"
                pattern="[0-9]*[.,]?[0-9]*"
                value={values.cost}
                onChange={(e) => setValues((v) => ({ ...v, cost: e.target.value }))}
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
