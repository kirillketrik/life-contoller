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
import { ApiError, foodItems, mealPlanEntries, recipes } from "@/lib/api";
import { FOOD_ITEMS_QUERY_KEY, MEAL_PLAN_ENTRIES_QUERY_KEY, RECIPES_QUERY_KEY } from "@/lib/query-keys";
import {
  type CreateMealPlanEntryInput,
  createMealPlanEntrySchema,
  type MealPlanEntry,
  type MealType,
} from "@/lib/types";

const MEAL_TYPES: MealType[] = ["breakfast", "lunch", "dinner", "snack"];

type ItemType = "foodItem" | "recipe";

function initialValues(entry: MealPlanEntry | undefined, defaultDate: string | undefined) {
  const itemType: ItemType = entry?.recipe ? "recipe" : "foodItem";
  return {
    date: entry?.date ?? defaultDate ?? new Date().toISOString().slice(0, 10),
    mealType: (entry?.meal_type ?? "breakfast") as MealType,
    itemType,
    foodItemId: entry?.food_item ? String(entry.food_item) : "",
    recipeId: entry?.recipe ? String(entry.recipe) : "",
    quantityG: entry?.quantity_g != null ? String(entry.quantity_g) : "",
    servings: entry?.servings != null ? String(entry.servings) : "",
  };
}

function parseDecimal(raw: string): number {
  return Number(raw.replace(",", "."));
}

/** Plans a new meal for a future day, or edits an existing plan when `entry`
 * is passed — same value-branching-by-presence-of-prop pattern as
 * MealEntryDialog, which this mirrors closely (itemType toggle, food-item/
 * recipe picker, quantity/servings input). The two differences: a `date`
 * input instead of `datetime`, and no `cost` field (not part of the
 * MealPlanEntry model). `defaultDate` seeds the date when planning from a
 * specific day in the week view. */
export function MealPlanEntryDialog({
  entry,
  defaultDate,
  trigger,
}: {
  entry?: MealPlanEntry;
  defaultDate?: string;
  trigger?: ReactElement;
}) {
  const t = useTranslations("mealPlanEntry");
  const tField = useTranslations("mealEntry");
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

  const { data: recipesData } = useQuery({
    queryKey: RECIPES_QUERY_KEY,
    queryFn: () => recipes.list(),
    enabled: open,
  });
  const availableRecipes = recipesData?.results ?? [];

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) setValues(initialValues(entry, defaultDate));
    setOpen(nextOpen);
  }

  const mutation = useMutation({
    mutationFn: (data: CreateMealPlanEntryInput) =>
      entry ? mealPlanEntries.update(entry.id, data) : mealPlanEntries.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MEAL_PLAN_ENTRIES_QUERY_KEY });
      toast.success(entry ? t("updated") : t("created"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : entry ? t("updateFailed") : t("createFailed"));
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (values.itemType === "foodItem" && !values.foodItemId) {
      toast.error(tField("foodItemRequired"));
      return;
    }
    if (values.itemType === "recipe" && !values.recipeId) {
      toast.error(tField("recipeRequired"));
      return;
    }
    const parsed = createMealPlanEntrySchema.safeParse({
      date: values.date,
      meal_type: values.mealType,
      food_item: values.itemType === "foodItem" ? Number(values.foodItemId) || null : null,
      recipe: values.itemType === "recipe" ? Number(values.recipeId) || null : null,
      quantity_g: values.itemType === "foodItem" ? parseDecimal(values.quantityG) : null,
      servings: values.itemType === "recipe" ? parseDecimal(values.servings) : null,
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
            <DialogTitle>{entry ? t("editTitle") : t("createTitle")}</DialogTitle>
            <DialogDescription>{entry ? t("editDescription") : t("createDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>{t("date")}</Label>
              <Input
                type="date"
                value={values.date}
                onChange={(e) => setValues((v) => ({ ...v, date: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>{tField("mealType")}</Label>
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
              <Label>{tField("itemType")}</Label>
              <Select
                items={{ foodItem: tField("itemTypeFoodItem"), recipe: tField("itemTypeRecipe") }}
                value={values.itemType}
                onValueChange={(v) =>
                  setValues((prev) => ({ ...prev, itemType: (v ?? "foodItem") as ItemType }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="foodItem">{tField("itemTypeFoodItem")}</SelectItem>
                  <SelectItem value="recipe">{tField("itemTypeRecipe")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {values.itemType === "foodItem" ? (
              <div className="space-y-2">
                <Label>{tField("foodItem")}</Label>
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
                    <SelectValue placeholder={tField("foodItemPlaceholder")} />
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
            ) : (
              <div className="space-y-2">
                <Label>{tField("recipe")}</Label>
                <Select
                  items={Object.fromEntries(availableRecipes.map((r) => [String(r.id), r.name]))}
                  value={values.recipeId}
                  onValueChange={(v) => setValues((prev) => ({ ...prev, recipeId: v ?? "" }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={tField("recipePlaceholder")} />
                  </SelectTrigger>
                  <SelectContent>
                    {availableRecipes.map((r) => (
                      <SelectItem key={r.id} value={String(r.id)}>
                        {r.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {values.itemType === "foodItem" ? (
              <div className="space-y-2">
                <Label htmlFor="mpe-quantity">{tField("quantity")}</Label>
                <Input
                  id="mpe-quantity"
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*[.,]?[0-9]*"
                  value={values.quantityG}
                  onChange={(e) => setValues((v) => ({ ...v, quantityG: e.target.value }))}
                  required
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="mpe-servings">{tField("servings")}</Label>
                <Input
                  id="mpe-servings"
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*[.,]?[0-9]*"
                  value={values.servings}
                  onChange={(e) => setValues((v) => ({ ...v, servings: e.target.value }))}
                  required
                />
              </div>
            )}
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
