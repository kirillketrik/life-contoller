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

export const ohlcBucketSchema = z.object({
  bucket_start: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  count: z.number(),
});
export type OHLCBucket = z.infer<typeof ohlcBucketSchema>;

export const rangeSummarySchema = z.object({
  min: z.number().nullable(),
  max: z.number().nullable(),
  avg: z.number().nullable(),
  count: z.number(),
});
export type RangeSummary = z.infer<typeof rangeSummarySchema>;

export const aggregateResponseSchema = z.object({
  metric_type: z.number(),
  range_start: z.string(),
  range_end: z.string(),
  timeframe_unit: timeframeUnitSchema,
  timeframe_count: z.number(),
  buckets: z.array(ohlcBucketSchema),
  summary: rangeSummarySchema,
  time_in_range_percent: z.number().nullable(),
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

export const favoriteMetricSchema = z.object({
  id: z.number(),
  order: z.number(),
  metric_type: metricTypeSchema,
  timeframe_unit: timeframeUnitSchema,
  buckets: z.array(ohlcBucketSchema),
  summary: rangeSummarySchema,
});
export type FavoriteMetric = z.infer<typeof favoriteMetricSchema>;

export const favoriteMetricListSchema = z.array(favoriteMetricSchema);
