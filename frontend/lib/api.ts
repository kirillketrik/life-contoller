import type { z } from "zod";

import {
  type AggregateResponse,
  aggregateResponseSchema,
  type BulkImportPreviewResponse,
  bulkImportPreviewResponseSchema,
  type BulkImportRequest,
  type BulkImportResultResponse,
  bulkImportResultResponseSchema,
  type CreateFoodItemInput,
  type CreateFormulaDefinitionInput,
  type CreateMealEntryInput,
  type CreateMealPlanEntryInput,
  type CreateMetricEntryInput,
  type CreateMetricImportSettingsInput,
  type CreateMetricThresholdInput,
  type CreateMetricTypeInput,
  type CreateRecipeInput,
  currentUserSchema,
  type DashboardElement,
  type DashboardElementInput,
  dashboardElementListSchema,
  dashboardElementSchema,
  type DashboardSummary,
  dashboardSummarySchema,
  type FoodItem,
  foodItemSchema,
  type FormulaDefinition,
  formulaDefinitionSchema,
  type FormulaNode,
  type FormulaPreviewResponse,
  formulaPreviewResponseSchema,
  type LoginInput,
  type MealEntry,
  mealEntrySchema,
  type MealPlanEntry,
  mealPlanEntrySchema,
  type MetricEntry,
  metricEntrySchema,
  type MetricImportSettings,
  metricImportSettingsOrNullSchema,
  metricImportSettingsSchema,
  type MetricThreshold,
  metricThresholdSchema,
  type MetricType,
  metricTypeSchema,
  type NutrientType,
  nutrientTypeSchema,
  type Paginated,
  paginatedSchema,
  type Recipe,
  recipeSchema,
  type TimeframeUnit,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(
      typeof body === "object" && body && "detail" in body ? String(body.detail) : "Request failed",
    );
    this.status = status;
    this.body = body;
  }
}

function getCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

async function request<Schema extends z.ZodTypeAny>(
  schema: Schema,
  path: string,
  init: RequestInit = {},
): Promise<z.infer<Schema>> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  const body = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, body);
  return schema.parse(body);
}

async function requestVoid(path: string, init: RequestInit = {}): Promise<void> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const csrfToken = getCookie("csrftoken");
  if (csrfToken) headers.set("X-CSRFToken", csrfToken);

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => undefined);
    throw new ApiError(response.status, body);
  }
}

export const auth = {
  me: () => request(currentUserSchema, "/api/auth/me/"),
  login: (data: LoginInput) =>
    request(currentUserSchema, "/api/auth/login/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  logout: () => requestVoid("/api/auth/logout/", { method: "POST" }),
};

export const metricTypes = {
  list: (): Promise<Paginated<MetricType>> =>
    request(paginatedSchema(metricTypeSchema), "/api/metric-types/"),
  get: (id: number): Promise<MetricType> =>
    request(metricTypeSchema, `/api/metric-types/${id}/`),
  create: (data: CreateMetricTypeInput): Promise<MetricType> =>
    request(metricTypeSchema, "/api/metric-types/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/metric-types/${id}/`, { method: "DELETE" }),
};

export const metricEntries = {
  list: (metricTypeId?: number): Promise<Paginated<MetricEntry>> =>
    request(
      paginatedSchema(metricEntrySchema),
      metricTypeId ? `/api/metric-entries/?metric_type=${metricTypeId}` : "/api/metric-entries/",
    ),
  create: (data: CreateMetricEntryInput): Promise<MetricEntry> =>
    request(metricEntrySchema, "/api/metric-entries/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: Partial<CreateMetricEntryInput>): Promise<MetricEntry> =>
    request(metricEntrySchema, `/api/metric-entries/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/metric-entries/${id}/`, { method: "DELETE" }),
};

export interface AggregateParams {
  timeframeUnit: TimeframeUnit;
  timeframeCount: number;
  start?: string;
  end?: string;
  relativeDays?: number;
}

function aggregateQueryString(params: AggregateParams): string {
  const query = new URLSearchParams({
    timeframe_unit: params.timeframeUnit,
    timeframe_count: String(params.timeframeCount),
  });
  if (params.start && params.end) {
    query.set("start", params.start);
    query.set("end", params.end);
  } else if (params.relativeDays) {
    query.set("relative_days", String(params.relativeDays));
  }
  return query.toString();
}

export const metricAggregate = {
  get: (metricTypeId: number, params: AggregateParams): Promise<AggregateResponse> =>
    request(
      aggregateResponseSchema,
      `/api/metric-types/${metricTypeId}/aggregate/?${aggregateQueryString(params)}`,
    ),
};

export const metricThresholds = {
  list: (): Promise<Paginated<MetricThreshold>> =>
    request(paginatedSchema(metricThresholdSchema), "/api/metric-thresholds/"),
  create: (data: CreateMetricThresholdInput): Promise<MetricThreshold> =>
    request(metricThresholdSchema, "/api/metric-thresholds/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: Partial<CreateMetricThresholdInput>): Promise<MetricThreshold> =>
    request(metricThresholdSchema, `/api/metric-thresholds/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/metric-thresholds/${id}/`, { method: "DELETE" }),
};

export const dashboardSummary = {
  get: (): Promise<DashboardSummary> => request(dashboardSummarySchema, "/api/dashboard-summary/"),
};

export const dashboardElements = {
  list: (): Promise<DashboardElement[]> =>
    request(dashboardElementListSchema, "/api/dashboard-elements/"),
  save: (metricTypeId: number, data: DashboardElementInput): Promise<DashboardElement> =>
    request(dashboardElementSchema, `/api/metric-types/${metricTypeId}/dashboard-element/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  remove: (metricTypeId: number) =>
    requestVoid(`/api/metric-types/${metricTypeId}/dashboard-element/`, { method: "DELETE" }),
  reorder: (metricTypeIds: number[]): Promise<DashboardElement[]> =>
    request(dashboardElementListSchema, "/api/dashboard-elements/reorder/", {
      method: "PATCH",
      body: JSON.stringify({ metric_type_ids: metricTypeIds }),
    }),
};

export const metricImportSettings = {
  get: (metricTypeId: number): Promise<MetricImportSettings | null> =>
    request(metricImportSettingsOrNullSchema, `/api/metric-types/${metricTypeId}/import-settings/`),
  set: (metricTypeId: number, data: CreateMetricImportSettingsInput): Promise<MetricImportSettings> =>
    request(metricImportSettingsSchema, `/api/metric-types/${metricTypeId}/import-settings/`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
};

export const metricBulkImport = {
  preview: (metricTypeId: number, data: BulkImportRequest): Promise<BulkImportPreviewResponse> =>
    request(bulkImportPreviewResponseSchema, `/api/metric-types/${metricTypeId}/import/preview/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  run: (metricTypeId: number, data: BulkImportRequest): Promise<BulkImportResultResponse> =>
    request(bulkImportResultResponseSchema, `/api/metric-types/${metricTypeId}/import/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export const nutrientTypes = {
  list: (): Promise<Paginated<NutrientType>> =>
    request(paginatedSchema(nutrientTypeSchema), "/api/nutrient-types/"),
};

export const foodItems = {
  list: (search?: string): Promise<Paginated<FoodItem>> =>
    request(
      paginatedSchema(foodItemSchema),
      search ? `/api/food-items/?search=${encodeURIComponent(search)}` : "/api/food-items/",
    ),
  get: (id: number): Promise<FoodItem> => request(foodItemSchema, `/api/food-items/${id}/`),
  create: (data: CreateFoodItemInput): Promise<FoodItem> =>
    request(foodItemSchema, "/api/food-items/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: CreateFoodItemInput): Promise<FoodItem> =>
    request(foodItemSchema, `/api/food-items/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/food-items/${id}/`, { method: "DELETE" }),
};

export const recipes = {
  list: (search?: string): Promise<Paginated<Recipe>> =>
    request(
      paginatedSchema(recipeSchema),
      search ? `/api/recipes/?search=${encodeURIComponent(search)}` : "/api/recipes/",
    ),
  get: (id: number): Promise<Recipe> => request(recipeSchema, `/api/recipes/${id}/`),
  create: (data: CreateRecipeInput): Promise<Recipe> =>
    request(recipeSchema, "/api/recipes/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: CreateRecipeInput): Promise<Recipe> =>
    request(recipeSchema, `/api/recipes/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/recipes/${id}/`, { method: "DELETE" }),
};

export const mealEntries = {
  list: (date?: string): Promise<Paginated<MealEntry>> =>
    request(
      paginatedSchema(mealEntrySchema),
      date ? `/api/meal-entries/?date=${date}` : "/api/meal-entries/",
    ),
  create: (data: CreateMealEntryInput): Promise<MealEntry> =>
    request(mealEntrySchema, "/api/meal-entries/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: CreateMealEntryInput): Promise<MealEntry> =>
    request(mealEntrySchema, `/api/meal-entries/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/meal-entries/${id}/`, { method: "DELETE" }),
};

export interface MealPlanEntryListParams {
  date?: string;
  startDate?: string;
  endDate?: string;
}

export const mealPlanEntries = {
  list: (params: MealPlanEntryListParams = {}): Promise<Paginated<MealPlanEntry>> => {
    const query = new URLSearchParams();
    if (params.date) query.set("date", params.date);
    if (params.startDate) query.set("start_date", params.startDate);
    if (params.endDate) query.set("end_date", params.endDate);
    const qs = query.toString();
    return request(
      paginatedSchema(mealPlanEntrySchema),
      qs ? `/api/meal-plan-entries/?${qs}` : "/api/meal-plan-entries/",
    );
  },
  create: (data: CreateMealPlanEntryInput): Promise<MealPlanEntry> =>
    request(mealPlanEntrySchema, "/api/meal-plan-entries/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: CreateMealPlanEntryInput): Promise<MealPlanEntry> =>
    request(mealPlanEntrySchema, `/api/meal-plan-entries/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/meal-plan-entries/${id}/`, { method: "DELETE" }),
  markEaten: (id: number): Promise<MealPlanEntry> =>
    request(mealPlanEntrySchema, `/api/meal-plan-entries/${id}/mark-eaten/`, { method: "POST" }),
};

export const formulaDefinitions = {
  list: (): Promise<Paginated<FormulaDefinition>> =>
    request(paginatedSchema(formulaDefinitionSchema), "/api/formula-definitions/"),
  create: (data: CreateFormulaDefinitionInput): Promise<FormulaDefinition> =>
    request(formulaDefinitionSchema, "/api/formula-definitions/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => requestVoid(`/api/formula-definitions/${id}/`, { method: "DELETE" }),
  preview: (expression: FormulaNode, computedMetricType?: number): Promise<FormulaPreviewResponse> =>
    request(formulaPreviewResponseSchema, "/api/formula-definitions/preview/", {
      method: "POST",
      body: JSON.stringify({ expression, computed_metric_type: computedMetricType ?? null }),
    }),
};
