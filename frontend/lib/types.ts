import { z } from "zod";

export const valueTypeSchema = z.enum(["number", "text", "boolean"]);
export type ValueType = z.infer<typeof valueTypeSchema>;

export const aggregationSchema = z.enum(["sum", "last", "avg", ""]);
export type Aggregation = z.infer<typeof aggregationSchema>;

export const metricTypeSchema = z.object({
  id: z.number(),
  name: z.string(),
  unit: z.string(),
  value_type: valueTypeSchema,
  aggregation: aggregationSchema,
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
