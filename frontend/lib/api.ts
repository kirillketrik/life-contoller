import type { z } from "zod";

import {
  type CreateMetricEntryInput,
  type CreateMetricTypeInput,
  currentUserSchema,
  type LoginInput,
  type MetricEntry,
  metricEntrySchema,
  type MetricType,
  metricTypeSchema,
  type Paginated,
  paginatedSchema,
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
  delete: (id: number) => requestVoid(`/api/metric-entries/${id}/`, { method: "DELETE" }),
};
