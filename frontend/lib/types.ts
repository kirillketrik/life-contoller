import { z } from "zod";

export const valueTypeSchema = z.enum(["number", "text", "boolean", "date"]);
export type ValueType = z.infer<typeof valueTypeSchema>;

export const aggregationSchema = z.enum(["sum", "last", "avg", ""]);
export type Aggregation = z.infer<typeof aggregationSchema>;

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
});
export type MetricType = z.infer<typeof metricTypeSchema>;

export const createMetricTypeSchema = z.object({
  name: z.string().trim().min(1, "Name is required"),
  unit: z.string().trim(),
  value_type: valueTypeSchema,
  aggregation: aggregationSchema,
  is_computed: z.boolean().optional(),
});
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

export const formulaKeySchema = z.enum(["bmi", "body_fat_navy", "tdee_mifflin"]);
export type FormulaKey = z.infer<typeof formulaKeySchema>;

export const FORMULA_INPUT_VARS: Record<FormulaKey, readonly string[]> = {
  bmi: ["weight_kg", "height_cm"],
  body_fat_navy: ["waist_cm", "neck_cm", "height_cm", "sex", "hip_cm"],
  tdee_mifflin: ["weight_kg", "height_cm", "dob", "sex", "activity_level"],
};

export const formulaDefinitionSchema = z.object({
  id: z.number(),
  computed_metric_type: z.number(),
  formula_key: formulaKeySchema,
  input_mapping: z.record(z.string(), z.number()),
  created_by: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type FormulaDefinition = z.infer<typeof formulaDefinitionSchema>;

export const createFormulaDefinitionSchema = z.object({
  computed_metric_type: z.number(),
  formula_key: formulaKeySchema,
  input_mapping: z.record(z.string(), z.number()),
});
export type CreateFormulaDefinitionInput = z.infer<typeof createFormulaDefinitionSchema>;
