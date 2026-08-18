---
name: architecture
description: Life Controller's architecture decisions and design patterns — the generalized metrics layer, selectors/permissions layering, formula strategy pattern, i18n routing, and the chart-library split. Use before any architecture/design work so new features fit the existing structure instead of introducing a competing pattern.
---

# Life Controller architecture

The canonical, always-current description of the domain model, layering, and permission rules
lives in the repo's own `CLAUDE.md` — read that first for the generalized metrics layer
(`MetricType`/`MetricEntry`/`MetricThreshold`/`FormulaDefinition`), the selectors/services
convention, and the permission table. This skill captures the *design decisions behind* that
structure and a few patterns CLAUDE.md doesn't spell out — use it to judge how a new feature
should fit in, not as a duplicate of the model docs.

## Backend patterns already in use

- **Selectors, not inline querysets.** Every read goes through a function in
  `apps/<app>/selectors.py`; views/viewsets never call `.objects.filter(...)` directly. This is
  where ownership/visibility rules live in one place per resource (e.g.
  `metric_entry_list_for_user` is the single place that decides "admins see everyone's, everyone
  else sees only their own").
- **Two permission patterns, chosen deliberately, not interchangeably**:
  - *Role-gated* (`MetricType`, `FormulaDefinition`): thin `DRF BasePermission` subclasses in
    `apps/metrics/permissions.py` that delegate to `apps.core.permissions.PermissionService.can()`.
    Use this when the resource is shared, global config that only a role (today: `admin`) should
    define.
    - *Ownership* (`MetricEntry`, `MetricThreshold`): the permission class checks
    `obj.owner_id == request.user.id` (or a `PermissionService.is_admin` override) directly, no
    `PermissionService` involved. Use this when the action is personal — every user manages their
    own data.
  - **The decision rule**: "does an admin *define what can be tracked*" → role-gated. "does a user
    *manage their own data*" → ownership. Don't add a third pattern; extend one of these two.
- **Strategy pattern for formulas.** `apps/metrics/formulas.py`'s `_FORMULA_COMPUTE` dict (formula
  key → compute function) plus `FORMULA_INPUT_VARS` (formula key → required input variable names)
  is a strategy-pattern dispatch table in everything but name. Adding a new formula means adding
  one entry to each — no new class hierarchy, no new abstraction. Keep it that way; don't refactor
  this into a class-per-formula pattern without a concrete reason (e.g. formulas needing their own
  state, which none currently do).
- **No repository layer, no `services.py` yet — by design, not by omission.** Reads go through
  selectors; writes are handled by serializer `create`/`update` (see e.g.
  `MetricEntrySerializer.create` setting `owner` from the request). A `services.py` per app is the
  documented next step *the first time write-side logic outgrows what a serializer method can
  reasonably hold* (CLAUDE.md's own words) — e.g. a write that touches multiple models
  transactionally, or has side effects beyond persistence. Don't add one preemptively; don't put
  multi-step write logic directly in a view once a real case shows up — that's when `services.py`
  gets introduced.
- **Aggregation is ORM-free by design.** `apps/metrics/aggregation.py` operates on plain
  `DataPoint` lists, not querysets — that's what lets the exact same bucketing/summary code serve
  both stored `MetricEntry` rows and on-the-fly `computed_series` output from formulas. Any new
  aggregation logic should extend this module's functions, not duplicate range-query logic in a
  view (see `points_for_metric_type` — one function, two data sources, same output shape).
- **One new read endpoint = one new selector function, not a new architectural layer.** The
  `dashboard-summary` endpoint (`selectors.dashboard_summary_for_user`) is the template: a plain
  dict-returning selector function, a thin `APIView` that calls it and wraps the result in
  `Response(...)`, scoped to the requesting user. No output serializer class was introduced for
  it — that matches the existing `/aggregate/` endpoint's convention (raw dict response), not a
  new pattern. Follow the same shape for the next aggregate-style endpoint.

## Frontend patterns already in use

- **`lib/api.ts` + `lib/types.ts` is the network boundary, not just form validation.** Every API
  call goes through the generic `request<Schema>(schema, path, init)` in `lib/api.ts`, which
  `schema.parse()`s the response — a malformed/unexpected API response fails loudly at the call
  site, not somewhere deep in a component. Add new endpoints as a new small object (`export const
  xThing = { get: () => request(xSchema, "/api/x/") }`), not as ad-hoc `fetch()` calls.
- **Zod schema + inferred type live together** in `lib/types.ts` (`export const xSchema = ...;
  export type X = z.infer<typeof xSchema>`), with separate, stricter schemas for create/input
  payloads than for read responses (see `metricTypeSchema` vs `createMetricTypeSchema`).
- **Query keys are plain factory functions/tuples** in `lib/query-keys.ts`, not a query-key
  library. A prefix-key helper (e.g. `metricAggregatePrefixKey`) is used when a mutation needs to
  invalidate a whole family of queries whose exact params aren't known at the call site.
- **Dialog pattern**: local `useState` per field → Zod `.safeParse` (where the payload shape
  benefits from it) → `useMutation` → `onSuccess` invalidates the relevant query key(s) and
  `toast.success(...)` → `onError` checks `error instanceof ApiError` and `toast.error(...)`. Every
  create/edit dialog in `components/metrics/` follows this; a new one should too.
- **i18n routing**: `next-intl` with `locales: ["ru"]`, `defaultLocale: "ru"`, `localePrefix:
  "as-needed"` (`frontend/i18n/routing.ts`) — Russian URLs stay unprefixed (`/metrics`, not
  `/ru/metrics`), so a second locale added later gets a `/en/...` prefix without touching existing
  links. All routes live under `app/[locale]/...`; the root layout (`app/[locale]/layout.tsx`) is
  the *only* layout — there's no separate `app/layout.tsx` above it (Next.js's root-layout
  requirement is satisfied by the outermost layout in the tree, which is this one, since every
  route lives under the `[locale]` segment). `middleware.ts`/`proxy.ts`: Next.js 16 renamed the
  middleware file convention to `proxy.ts` — this repo already uses `proxy.ts`; don't reintroduce
  a `middleware.ts`.
- **Chart library split (a deliberate decision, not an oversight)**: Lightweight Charts
  (`components/metrics/metric-chart.tsx`, `components/dashboard/monthly-trend-chart.tsx`) is a
  *time-scale* library — use it for genuinely time-series data (an x-axis that's a timeline).
  Categorical breakdowns (label → count, no time axis) use a plain Tailwind bar component
  (`components/dashboard/horizontal-bar-list.tsx`) instead — forcing a time-series chart library to
  fake a categorical axis is worse than a five-line custom component, and pulling in a second
  charting dependency for one simple visual isn't worth it either. When adding a new chart, decide
  which bucket the data falls into *before* picking a component — see the `dashboard-chart-card`
  skill.

## When a new pattern might actually be warranted

Don't reach for a design pattern because it's available — CLAUDE.md and this skill both favor the
plainest structure that works. A new pattern (repository, factory, a real service layer, a formula
class hierarchy) is worth introducing when a *concrete* requirement doesn't fit the existing
shape — e.g. a write that must be transactional across models, a formula that needs per-instance
state, or a data source that needs swapping at runtime. Document the decision in CLAUDE.md's
"Architectural decisions" note when you do, the same way the chart-library split and the
i18n-routing choice are documented there.
