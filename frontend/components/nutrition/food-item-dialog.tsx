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
import { ApiError, foodItems, nutrientTypes } from "@/lib/api";
import { FOOD_ITEMS_QUERY_KEY, NUTRIENT_TYPES_QUERY_KEY } from "@/lib/query-keys";
import { type CreateFoodItemInput, createFoodItemSchema, type FoodItem } from "@/lib/types";

interface NutrientValueRow {
  nutrientTypeId: string;
  amount: string;
}

function emptyNutrientRow(): NutrientValueRow {
  return { nutrientTypeId: "", amount: "" };
}

function toDecimalInput(value: number): string {
  return String(value);
}

function initialValues(item: FoodItem | undefined) {
  return {
    name: item?.name ?? "",
    brand: item?.brand ?? "",
    calories: item ? toDecimalInput(item.calories_per_100g) : "",
    protein: item ? toDecimalInput(item.protein_per_100g) : "",
    fat: item ? toDecimalInput(item.fat_per_100g) : "",
    carbs: item ? toDecimalInput(item.carbs_per_100g) : "",
    nutrientRows: (item?.nutrient_values ?? []).map((v) => ({
      nutrientTypeId: String(v.nutrient_type),
      amount: toDecimalInput(v.amount_per_100g),
    })),
  };
}

function parseDecimal(raw: string): number {
  return Number(raw.replace(",", "."));
}

/** Creates a new food item, or edits an existing one when `item` is passed —
 * same value-branching-by-presence-of-prop pattern as MetricEntryDialog. */
export function FoodItemDialog({
  item,
  trigger,
}: {
  item?: FoodItem;
  trigger?: ReactElement;
}) {
  const t = useTranslations("foodItem");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(() => initialValues(item));

  const { data: nutrientTypesData } = useQuery({
    queryKey: NUTRIENT_TYPES_QUERY_KEY,
    queryFn: () => nutrientTypes.list(),
    enabled: open,
  });
  const availableNutrientTypes = nutrientTypesData?.results ?? [];

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) setValues(initialValues(item));
    setOpen(nextOpen);
  }

  const mutation = useMutation({
    mutationFn: (data: CreateFoodItemInput) =>
      item ? foodItems.update(item.id, data) : foodItems.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FOOD_ITEMS_QUERY_KEY });
      toast.success(item ? t("updated") : t("created"));
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : item ? t("updateFailed") : t("createFailed"));
    },
  });

  function updateNutrientRow(index: number, patch: Partial<NutrientValueRow>) {
    setValues((v) => ({
      ...v,
      nutrientRows: v.nutrientRows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
  }

  function addNutrientRow() {
    setValues((v) => ({ ...v, nutrientRows: [...v.nutrientRows, emptyNutrientRow()] }));
  }

  function removeNutrientRow(index: number) {
    setValues((v) => ({ ...v, nutrientRows: v.nutrientRows.filter((_, i) => i !== index) }));
  }

  function buildPayload() {
    return {
      name: values.name,
      brand: values.brand,
      calories_per_100g: parseDecimal(values.calories),
      protein_per_100g: parseDecimal(values.protein),
      fat_per_100g: parseDecimal(values.fat),
      carbs_per_100g: parseDecimal(values.carbs),
      nutrient_values: values.nutrientRows
        .filter((row) => row.nutrientTypeId && row.amount.trim())
        .map((row) => ({
          nutrient_type: Number(row.nutrientTypeId),
          amount_per_100g: parseDecimal(row.amount),
        })),
    };
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const parsed = createFoodItemSchema.safeParse(buildPayload());
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? t("invalid"));
      return;
    }
    mutation.mutate(parsed.data);
  }

  const usedNutrientTypeIds = new Set(values.nutrientRows.map((row) => row.nutrientTypeId));

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={trigger ?? <Button>{t("new")}</Button>} />
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{item ? t("editTitle") : t("createTitle")}</DialogTitle>
            <DialogDescription>{t("createDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="fi-name">{t("name")}</Label>
              <Input
                id="fi-name"
                value={values.name}
                onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="fi-brand">{t("brand")}</Label>
              <Input
                id="fi-brand"
                value={values.brand}
                onChange={(e) => setValues((v) => ({ ...v, brand: e.target.value }))}
              />
            </div>
            <p className="text-xs text-muted-foreground">{t("per100gHint")}</p>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="fi-calories">{t("calories")}</Label>
                <Input
                  id="fi-calories"
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*[.,]?[0-9]*"
                  value={values.calories}
                  onChange={(e) => setValues((v) => ({ ...v, calories: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="fi-protein">{t("protein")}</Label>
                <Input
                  id="fi-protein"
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*[.,]?[0-9]*"
                  value={values.protein}
                  onChange={(e) => setValues((v) => ({ ...v, protein: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="fi-fat">{t("fat")}</Label>
                <Input
                  id="fi-fat"
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*[.,]?[0-9]*"
                  value={values.fat}
                  onChange={(e) => setValues((v) => ({ ...v, fat: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="fi-carbs">{t("carbs")}</Label>
                <Input
                  id="fi-carbs"
                  type="text"
                  inputMode="decimal"
                  pattern="[0-9]*[.,]?[0-9]*"
                  value={values.carbs}
                  onChange={(e) => setValues((v) => ({ ...v, carbs: e.target.value }))}
                  required
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t("nutrients")}</Label>
              <div className="space-y-2">
                {values.nutrientRows.map((row, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Select
                      items={Object.fromEntries(
                        availableNutrientTypes.map((nt) => [String(nt.id), `${nt.name} (${nt.unit})`]),
                      )}
                      value={row.nutrientTypeId}
                      onValueChange={(v) => updateNutrientRow(index, { nutrientTypeId: v ?? "" })}
                    >
                      <SelectTrigger className="flex-1">
                        <SelectValue placeholder={t("nutrientPlaceholder")} />
                      </SelectTrigger>
                      <SelectContent>
                        {availableNutrientTypes.map((nt) => (
                          <SelectItem
                            key={nt.id}
                            value={String(nt.id)}
                            disabled={usedNutrientTypeIds.has(String(nt.id)) && row.nutrientTypeId !== String(nt.id)}
                          >
                            {nt.name} ({nt.unit})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      type="text"
                      inputMode="decimal"
                      pattern="[0-9]*[.,]?[0-9]*"
                      placeholder={t("amountPlaceholder")}
                      value={row.amount}
                      onChange={(e) => updateNutrientRow(index, { amount: e.target.value })}
                      className="w-28"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => removeNutrientRow(index)}
                      aria-label={t("removeNutrient")}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
              <Button type="button" variant="outline" size="sm" onClick={addNutrientRow}>
                <Plus className="size-4" />
                {t("addNutrient")}
              </Button>
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
