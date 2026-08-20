"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
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
import { ApiError, foodItems, recipes } from "@/lib/api";
import { FOOD_ITEMS_QUERY_KEY, RECIPES_QUERY_KEY } from "@/lib/query-keys";
import { type CreateRecipeInput, createRecipeSchema, type Recipe } from "@/lib/types";

interface IngredientRow {
  foodItemId: string;
  quantityG: string;
}

function emptyIngredientRow(): IngredientRow {
  return { foodItemId: "", quantityG: "" };
}

function initialValues(recipe: Recipe | undefined) {
  return {
    name: recipe?.name ?? "",
    servings: recipe ? String(recipe.servings) : "1",
    cost: recipe?.cost != null ? String(recipe.cost) : "",
    ingredientRows: (recipe?.ingredients ?? []).map((ingredient) => ({
      foodItemId: String(ingredient.food_item),
      quantityG: String(ingredient.quantity_g),
    })),
  };
}

function parseDecimal(raw: string): number {
  return Number(raw.replace(",", "."));
}

/** Creates a new recipe, or edits an existing one when `recipe` is passed —
 * same value-branching-by-presence-of-prop pattern as FoodItemDialog. */
export function RecipeDialog({
  recipe,
  trigger,
}: {
  recipe?: Recipe;
  trigger?: ReactElement;
}) {
  const t = useTranslations("recipe");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(() => initialValues(recipe));

  const { data: foodItemsData } = useQuery({
    queryKey: FOOD_ITEMS_QUERY_KEY,
    queryFn: () => foodItems.list(),
    enabled: open,
  });
  const availableFoodItems = foodItemsData?.results ?? [];

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) setValues(initialValues(recipe));
    setOpen(nextOpen);
  }

  const mutation = useMutation({
    mutationFn: (data: CreateRecipeInput) =>
      recipe ? recipes.update(recipe.id, data) : recipes.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: RECIPES_QUERY_KEY });
      toast.success(recipe ? t("updated") : t("created"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiError ? error.message : recipe ? t("updateFailed") : t("createFailed"),
      );
    },
  });

  function updateIngredientRow(index: number, patch: Partial<IngredientRow>) {
    setValues((v) => ({
      ...v,
      ingredientRows: v.ingredientRows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
  }

  function addIngredientRow() {
    setValues((v) => ({ ...v, ingredientRows: [...v.ingredientRows, emptyIngredientRow()] }));
  }

  function removeIngredientRow(index: number) {
    setValues((v) => ({ ...v, ingredientRows: v.ingredientRows.filter((_, i) => i !== index) }));
  }

  function buildPayload() {
    return {
      name: values.name,
      servings: Number(values.servings),
      cost: values.cost.trim() ? parseDecimal(values.cost) : null,
      ingredients: values.ingredientRows
        .filter((row) => row.foodItemId && row.quantityG.trim())
        .map((row) => ({
          food_item: Number(row.foodItemId),
          quantity_g: parseDecimal(row.quantityG),
        })),
    };
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const parsed = createRecipeSchema.safeParse(buildPayload());
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? t("invalid"));
      return;
    }
    mutation.mutate(parsed.data);
  }

  // Live client-side estimate — the same per-100g x quantity/100 arithmetic
  // the backend uses, computed here purely so the user sees a running total
  // while building the recipe, before it's ever saved.
  const estimatedCalories = values.ingredientRows.reduce((sum, row) => {
    const item = availableFoodItems.find((fi) => String(fi.id) === row.foodItemId);
    const quantity = parseDecimal(row.quantityG);
    if (!item || !Number.isFinite(quantity)) return sum;
    return sum + (item.calories_per_100g * quantity) / 100;
  }, 0);

  const usedFoodItemIds = new Set(values.ingredientRows.map((row) => row.foodItemId));

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={trigger ?? <Button>{t("new")}</Button>} />
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{recipe ? t("editTitle") : t("createTitle")}</DialogTitle>
            <DialogDescription>{t("createDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="r-name">{t("name")}</Label>
              <Input
                id="r-name"
                value={values.name}
                onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="r-servings">{t("servings")}</Label>
                <Input
                  id="r-servings"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={values.servings}
                  onChange={(e) => setValues((v) => ({ ...v, servings: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="r-cost">{t("cost")}</Label>
                <Input
                  id="r-cost"
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*[.,]?[0-9]*"
                  value={values.cost}
                  onChange={(e) => setValues((v) => ({ ...v, cost: e.target.value }))}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t("ingredients")}</Label>
              <div className="space-y-2">
                {values.ingredientRows.map((row, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Select
                      items={Object.fromEntries(
                        availableFoodItems.map((fi) => [String(fi.id), fi.name]),
                      )}
                      value={row.foodItemId}
                      onValueChange={(v) => updateIngredientRow(index, { foodItemId: v ?? "" })}
                    >
                      <SelectTrigger className="flex-1">
                        <SelectValue placeholder={t("foodItemPlaceholder")} />
                      </SelectTrigger>
                      <SelectContent>
                        {availableFoodItems.map((fi) => (
                          <SelectItem
                            key={fi.id}
                            value={String(fi.id)}
                            disabled={
                              usedFoodItemIds.has(String(fi.id)) && row.foodItemId !== String(fi.id)
                            }
                          >
                            {fi.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      type="text"
                      inputMode="decimal"
                      pattern="[0-9]*[.,]?[0-9]*"
                      placeholder={t("quantityPlaceholder")}
                      value={row.quantityG}
                      onChange={(e) => updateIngredientRow(index, { quantityG: e.target.value })}
                      className="w-28"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => removeIngredientRow(index)}
                      aria-label={t("removeIngredient")}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
              <Button type="button" variant="outline" size="sm" onClick={addIngredientRow}>
                <Plus className="size-4" />
                {t("addIngredient")}
              </Button>
            </div>
            {values.ingredientRows.length > 0 && (
              <p className="text-sm text-muted-foreground">
                {t("estimatedCalories", { value: Math.round(estimatedCalories) })}
              </p>
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
