import { z } from "zod";

export const valueTypeSchema = z.enum(["number", "text", "boolean", "date", "choice"]);
export type ValueType = z.infer<typeof valueTypeSchema>;

export const aggregationSchema = z.enum(["sum", "last", "avg", ""]);
export type Aggregation = z.infer<typeof aggregationSchema>;

export const choiceOptionSchema = z.object({
  id: z.number(),
  code: z.string(),
  label: z.string(),
  numeric_value: z.number().nullable(),
  order: z.number(),
});
export type ChoiceOption = z.infer<typeof choiceOptionSchema>;

export const metricTypeSchema = z.object({
  id: z.number(),
  name: z.string(),
  unit: z.string(),
  value_type: valueTypeSchema,
  aggregation: aggregationSchema,
  is_computed: z.boolean(),
  is_singleton: z.boolean(),
  created_by: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  choices: z.array(choiceOptionSchema),
});
export type MetricType = z.infer<typeof metricTypeSchema>;

export const createChoiceOptionSchema = z.object({
  code: z.string().trim().min(1, "Code is required"),
  label: z.string().trim().min(1, "Label is required"),
  numeric_value: z.number().nullable().optional(),
  order: z.number(),
});
export type CreateChoiceOptionInput = z.infer<typeof createChoiceOptionSchema>;

export const createMetricTypeSchema = z
  .object({
    name: z.string().trim().min(1, "Name is required"),
    unit: z.string().trim(),
    value_type: valueTypeSchema,
    aggregation: aggregationSchema,
    is_computed: z.boolean().optional(),
    is_singleton: z.boolean().optional(),
    choices: z.array(createChoiceOptionSchema).optional(),
  })
  .refine(
    (data) => {
      if (data.value_type !== "choice") return true;
      const choices = data.choices ?? [];
      if (choices.length === 0) return false;
      const codes = choices.map((choice) => choice.code);
      return new Set(codes).size === codes.length;
    },
    { message: "A choice metric type needs at least one option with a unique code", path: ["choices"] },
  );
export type CreateMetricTypeInput = z.infer<typeof createMetricTypeSchema>;

export const metricValueSchema = z.union([z.number(), z.string(), z.boolean()]);

export const metricEntrySchema = z.object({
  id: z.number(),
  metric_type: z.number(),
  metric_type_name: z.string(),
  owner: z.number(),
  value: metricValueSchema,
  context: z.record(z.string(), z.unknown()).nullable(),
  recorded_at: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type MetricEntry = z.infer<typeof metricEntrySchema>;

export const createMetricEntrySchema = z.object({
  metric_type: z.number(),
  value: metricValueSchema,
  context: z.record(z.string(), z.unknown()).nullable().optional(),
  recorded_at: z.string(),
});
export type CreateMetricEntryInput = z.infer<typeof createMetricEntrySchema>;

export const currentUserSchema = z.object({
  id: z.number(),
  username: z.string(),
  email: z.string(),
  is_admin: z.boolean(),
});
export type CurrentUser = z.infer<typeof currentUserSchema>;

export const loginInputSchema = z.object({
  username: z.string().trim().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});
export type LoginInput = z.infer<typeof loginInputSchema>;

export function paginatedSchema<T extends z.ZodTypeAny>(item: T) {
  return z.object({
    count: z.number(),
    next: z.string().nullable(),
    previous: z.string().nullable(),
    results: z.array(item),
  });
}
export type Paginated<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export const timeframeUnitSchema = z.enum(["minute", "hour", "day", "week", "month", "year"]);
export type TimeframeUnit = z.infer<typeof timeframeUnitSchema>;

export const metricDataPointSchema = z.object({
  timestamp: z.string(),
  value: z.number(),
});
export type MetricDataPoint = z.infer<typeof metricDataPointSchema>;

export const rangeSummarySchema = z.object({
  min: z.number().nullable(),
  max: z.number().nullable(),
  avg: z.number().nullable(),
  count: z.number(),
});
export type RangeSummary = z.infer<typeof rangeSummarySchema>;

/** The 24h/7d/30d/3m/1y KPI badges shown next to a metric's name — always
 * "as of now", independent of whatever display timeframe a chart is
 * currently showing. `null` per period when there's no data far enough
 * back to compare against. */
export const periodChangesSchema = z.object({
  "24h": z.number().nullable(),
  "7d": z.number().nullable(),
  "30d": z.number().nullable(),
  "3m": z.number().nullable(),
  "1y": z.number().nullable(),
});
export type PeriodChanges = z.infer<typeof periodChangesSchema>;

/** A metric's configured "healthy range" bounds, as returned alongside a
 * chart's point series so the chart can draw them as bound lines without a
 * second request — either bound may be null independently, same as
 * `MetricThreshold` itself. */
export const thresholdBoundsSchema = z.object({
  lower_bound: z.number().nullable(),
  upper_bound: z.number().nullable(),
});
export type ThresholdBounds = z.infer<typeof thresholdBoundsSchema>;

export const aggregateResponseSchema = z.object({
  metric_type: z.number(),
  range_start: z.string(),
  range_end: z.string(),
  timeframe_unit: timeframeUnitSchema,
  timeframe_count: z.number(),
  current: z.number().nullable(),
  points: z.array(metricDataPointSchema),
  summary: rangeSummarySchema,
  time_in_range_percent: z.number().nullable(),
  threshold: thresholdBoundsSchema.nullable(),
  period_changes: periodChangesSchema,
});
export type AggregateResponse = z.infer<typeof aggregateResponseSchema>;

export const metricThresholdSchema = z.object({
  id: z.number(),
  metric_type: z.number(),
  user: z.number(),
  lower_bound: z.number().nullable(),
  upper_bound: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type MetricThreshold = z.infer<typeof metricThresholdSchema>;

export const createMetricThresholdSchema = z
  .object({
    metric_type: z.number(),
    lower_bound: z.number().nullable().optional(),
    upper_bound: z.number().nullable().optional(),
  })
  .refine((data) => data.lower_bound != null || data.upper_bound != null, {
    message: "Set at least one of lower or upper bound",
  });
export type CreateMetricThresholdInput = z.infer<typeof createMetricThresholdSchema>;

export const BINARY_OPS = ["+", "-", "*", "/", "^"] as const;
export const UNARY_OPS = ["sqrt", "abs", "neg"] as const;
export const FUNCTION_NAMES = ["min", "max", "round", "age", "log10"] as const;
export const COMPARISON_OPS = ["==", "!=", "<", ">", "<=", ">="] as const;

export type BinaryOp = (typeof BINARY_OPS)[number];
export type UnaryOp = (typeof UNARY_OPS)[number];
export type FunctionName = (typeof FUNCTION_NAMES)[number];
export type ComparisonOp = (typeof COMPARISON_OPS)[number];

/** Mirrors `apps.metrics.formula_engine.nodes` 1:1 — see that module for the
 * authoritative schema. Stored as JSON on `FormulaDefinition.expression`;
 * never evaluated as a string on either side. */
export type FormulaNode =
  | { type: "metric"; metric_type_id: number }
  | { type: "constant"; value: number | string | boolean | null }
  | { type: "binary_op"; op: BinaryOp; left: FormulaNode; right: FormulaNode }
  | { type: "unary_op"; op: UnaryOp; operand: FormulaNode }
  | { type: "function"; name: FunctionName; args: FormulaNode[] }
  | { type: "comparison"; op: ComparisonOp; left: FormulaNode; right: FormulaNode }
  | { type: "conditional"; condition: FormulaNode; then: FormulaNode; else: FormulaNode };

export const formulaNodeSchema: z.ZodType<FormulaNode> = z.lazy(() =>
  z.discriminatedUnion("type", [
    z.object({ type: z.literal("metric"), metric_type_id: z.number() }),
    z.object({
      type: z.literal("constant"),
      value: z.union([z.number(), z.string(), z.boolean(), z.null()]),
    }),
    z.object({
      type: z.literal("binary_op"),
      op: z.enum(BINARY_OPS),
      left: formulaNodeSchema,
      right: formulaNodeSchema,
    }),
    z.object({
      type: z.literal("unary_op"),
      op: z.enum(UNARY_OPS),
      operand: formulaNodeSchema,
    }),
    z.object({
      type: z.literal("function"),
      name: z.enum(FUNCTION_NAMES),
      args: z.array(formulaNodeSchema),
    }),
    z.object({
      type: z.literal("comparison"),
      op: z.enum(COMPARISON_OPS),
      left: formulaNodeSchema,
      right: formulaNodeSchema,
    }),
    z.object({
      type: z.literal("conditional"),
      condition: formulaNodeSchema,
      then: formulaNodeSchema,
      else: formulaNodeSchema,
    }),
  ]),
);

export const formulaDefinitionSchema = z.object({
  id: z.number(),
  computed_metric_type: z.number(),
  expression: formulaNodeSchema,
  created_by: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type FormulaDefinition = z.infer<typeof formulaDefinitionSchema>;

export const createFormulaDefinitionSchema = z.object({
  computed_metric_type: z.number(),
  expression: formulaNodeSchema,
});
export type CreateFormulaDefinitionInput = z.infer<typeof createFormulaDefinitionSchema>;

export const formulaErrorSchema = z.object({
  code: z.string(),
  detail: z.string().optional(),
});
export type FormulaValidationError = z.infer<typeof formulaErrorSchema>;

export const formulaPreviewResponseSchema = z.object({
  value: z.union([z.number(), z.string(), z.boolean(), z.null()]),
  errors: z.array(formulaErrorSchema),
});
export type FormulaPreviewResponse = z.infer<typeof formulaPreviewResponseSchema>;

export const dashboardEntriesByTypeSchema = z.object({
  metric_type_name: z.string(),
  count: z.number(),
});

export const dashboardEntriesByMonthSchema = z.object({
  month: z.string(),
  count: z.number(),
});

export const dashboardSummarySchema = z.object({
  metric_type_count: z.number(),
  entry_count: z.number(),
  threshold_count: z.number(),
  entries_by_metric_type: z.array(dashboardEntriesByTypeSchema),
  entries_by_month: z.array(dashboardEntriesByMonthSchema),
});
export type DashboardSummary = z.infer<typeof dashboardSummarySchema>;

export const dashboardElementTimeframeSchema = z.enum([
  "7d",
  "30d",
  "90d",
  "1y",
  "3y",
  "all",
  "custom",
]);
export type DashboardElementTimeframe = z.infer<typeof dashboardElementTimeframeSchema>;

export const dashboardElementSchema = z.object({
  id: z.number(),
  order: z.number(),
  metric_type: metricTypeSchema,
  show_chart: z.boolean(),
  show_current: z.boolean(),
  show_max: z.boolean(),
  show_min: z.boolean(),
  show_avg: z.boolean(),
  show_time_in_range: z.boolean(),
  timeframe: dashboardElementTimeframeSchema,
  custom_range_start: z.string().nullable(),
  custom_range_end: z.string().nullable(),
  current: z.number().nullable(),
  max: z.number().nullable(),
  min: z.number().nullable(),
  avg: z.number().nullable(),
  time_in_range_percent: z.number().nullable(),
  points: z.array(metricDataPointSchema),
  timeframe_unit: timeframeUnitSchema.nullable(),
  threshold: thresholdBoundsSchema.nullable(),
  period_changes: periodChangesSchema,
});
export type DashboardElement = z.infer<typeof dashboardElementSchema>;

export const dashboardElementListSchema = z.array(dashboardElementSchema);

export const dashboardElementInputSchema = z
  .object({
    show_chart: z.boolean(),
    show_current: z.boolean(),
    show_max: z.boolean(),
    show_min: z.boolean(),
    show_avg: z.boolean(),
    show_time_in_range: z.boolean(),
    timeframe: dashboardElementTimeframeSchema,
    custom_range_start: z.string().nullable(),
    custom_range_end: z.string().nullable(),
  })
  .refine(
    (data) =>
      data.show_chart ||
      data.show_current ||
      data.show_max ||
      data.show_min ||
      data.show_avg ||
      data.show_time_in_range,
    { message: "Enable at least one element", path: ["show_chart"] },
  )
  .refine(
    (data) =>
      data.timeframe !== "custom" || (data.custom_range_start !== null && data.custom_range_end !== null),
    { message: "A custom timeframe needs both start and end dates", path: ["custom_range_start"] },
  )
  .refine(
    (data) =>
      data.timeframe !== "custom" ||
      data.custom_range_start === null ||
      data.custom_range_end === null ||
      data.custom_range_start <= data.custom_range_end,
    { message: "Start date must not be after end date", path: ["custom_range_start"] },
  );
export type DashboardElementInput = z.infer<typeof dashboardElementInputSchema>;

export const metricImportSettingsSchema = z.object({
  id: z.number(),
  metric_type: z.number(),
  user: z.number(),
  template: z.string(),
  separator: z.string(),
  date_format: z.string(),
  decimal_separator: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type MetricImportSettings = z.infer<typeof metricImportSettingsSchema>;

export const metricImportSettingsOrNullSchema = metricImportSettingsSchema.nullable();

export const createMetricImportSettingsSchema = z.object({
  template: z.string().trim().min(1, "Template is required"),
  separator: z.string().min(1, "Separator is required"),
  date_format: z.string().trim().min(1, "Date format is required"),
  decimal_separator: z.enum([".", ","]),
});
export type CreateMetricImportSettingsInput = z.infer<typeof createMetricImportSettingsSchema>;

export const bulkImportDuplicatePolicySchema = z.enum(["skip", "overwrite"]);
export type BulkImportDuplicatePolicy = z.infer<typeof bulkImportDuplicatePolicySchema>;

export const bulkImportItemInputSchema = z.object({
  value: z.string().nullable(),
  date: z.string().nullable(),
});
export type BulkImportItemInput = z.infer<typeof bulkImportItemInputSchema>;

export const bulkImportRequestSchema = z.object({
  items: z.array(bulkImportItemInputSchema).min(1),
  date_format: z.string(),
  decimal_separator: z.enum([".", ","]),
  duplicate_policy: bulkImportDuplicatePolicySchema,
});
export type BulkImportRequest = z.infer<typeof bulkImportRequestSchema>;

export const bulkImportItemStatusSchema = z.enum([
  "new",
  "duplicate_skip",
  "duplicate_overwrite",
  "invalid",
]);
export type BulkImportItemStatus = z.infer<typeof bulkImportItemStatusSchema>;

export const bulkImportItemResultSchema = z.object({
  line_number: z.number(),
  raw_value: z.string().nullable(),
  raw_date: z.string().nullable(),
  value: z.union([z.number(), z.string(), z.boolean()]).nullable(),
  recorded_at: z.string().nullable(),
  status: bulkImportItemStatusSchema,
  error_code: z.string().nullable(),
});
export type BulkImportItemResult = z.infer<typeof bulkImportItemResultSchema>;

export const bulkImportPreviewResponseSchema = z.object({
  items: z.array(bulkImportItemResultSchema),
});
export type BulkImportPreviewResponse = z.infer<typeof bulkImportPreviewResponseSchema>;

export const bulkImportResultResponseSchema = z.object({
  created_count: z.number(),
  updated_count: z.number(),
  skipped_count: z.number(),
  invalid_count: z.number(),
  items: z.array(bulkImportItemResultSchema),
});
export type BulkImportResultResponse = z.infer<typeof bulkImportResultResponseSchema>;

// --- Nutrition module ---

export const nutrientCategorySchema = z.enum(["macro", "micro"]);
export type NutrientCategory = z.infer<typeof nutrientCategorySchema>;

export const nutrientTypeSchema = z.object({
  id: z.number(),
  name: z.string(),
  unit: z.string(),
  category: nutrientCategorySchema,
  is_system: z.boolean(),
  created_at: z.string(),
});
export type NutrientType = z.infer<typeof nutrientTypeSchema>;

export const foodSourceSchema = z.enum(["own", "external"]);
export type FoodSource = z.infer<typeof foodSourceSchema>;

/** Decimal fields come back from DRF as numeric strings — parsed to numbers
 * here so the frontend never has to think about which fields are Decimals
 * on the Django side. */
const decimalStringSchema = z.union([z.string(), z.number()]).pipe(z.coerce.number());

export const foodNutrientValueSchema = z.object({
  id: z.number(),
  nutrient_type: z.number(),
  nutrient_type_name: z.string(),
  nutrient_type_unit: z.string(),
  amount_per_100g: decimalStringSchema,
});
export type FoodNutrientValue = z.infer<typeof foodNutrientValueSchema>;

export const foodItemSchema = z.object({
  id: z.number(),
  owner: z.number(),
  name: z.string(),
  brand: z.string(),
  source: foodSourceSchema,
  external_id: z.string(),
  calories_per_100g: decimalStringSchema,
  protein_per_100g: decimalStringSchema,
  fat_per_100g: decimalStringSchema,
  carbs_per_100g: decimalStringSchema,
  is_verified: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  nutrient_values: z.array(foodNutrientValueSchema),
});
export type FoodItem = z.infer<typeof foodItemSchema>;

export const createFoodNutrientValueSchema = z.object({
  nutrient_type: z.number(),
  amount_per_100g: z.number(),
});
export type CreateFoodNutrientValueInput = z.infer<typeof createFoodNutrientValueSchema>;

export const createFoodItemSchema = z
  .object({
    name: z.string().trim().min(1, "Name is required"),
    brand: z.string().trim(),
    calories_per_100g: z.number().min(0),
    protein_per_100g: z.number().min(0),
    fat_per_100g: z.number().min(0),
    carbs_per_100g: z.number().min(0),
    nutrient_values: z.array(createFoodNutrientValueSchema).optional(),
  })
  .refine(
    (data) => {
      const ids = (data.nutrient_values ?? []).map((v) => v.nutrient_type);
      return new Set(ids).size === ids.length;
    },
    { message: "Each nutrient may only be set once", path: ["nutrient_values"] },
  );
export type CreateFoodItemInput = z.infer<typeof createFoodItemSchema>;

export const mealTypeSchema = z.enum(["breakfast", "lunch", "dinner", "snack"]);
export type MealType = z.infer<typeof mealTypeSchema>;

export const mealEntrySchema = z.object({
  id: z.number(),
  owner: z.number(),
  datetime: z.string(),
  meal_type: mealTypeSchema,
  food_item: z.number(),
  food_item_name: z.string(),
  quantity_g: decimalStringSchema,
  cost: decimalStringSchema.nullable(),
  calories: decimalStringSchema,
  protein: decimalStringSchema,
  fat: decimalStringSchema,
  carbs: decimalStringSchema,
  created_at: z.string(),
  updated_at: z.string(),
});
export type MealEntry = z.infer<typeof mealEntrySchema>;

export const createMealEntrySchema = z.object({
  datetime: z.string(),
  meal_type: mealTypeSchema,
  food_item: z.number(),
  quantity_g: z.number().positive(),
  cost: z.number().nullable().optional(),
});
export type CreateMealEntryInput = z.infer<typeof createMealEntrySchema>;
