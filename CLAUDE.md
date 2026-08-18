# Life Controller — CLAUDE.md

This file is living documentation for Claude Code (and any other contributor) working in this
repository. Update it in the same commit/PR that introduces a meaningful change: new modules,
architectural decisions, conventions, or major dependencies.

## Project overview

Life Controller is a personal life-tracking application, built incrementally, one feature at a
time. It will eventually cover multiple related domains:

- Body measurements
- Custom health metrics (including dose/injection logging)
- Nutrition
- Workouts
- Finances

Domains influence each other (finances → nutrition → workouts), but each is built as its own
feature branch on top of a shared foundation — the **generalized metrics layer** (see below) is
that foundation.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Django + Django REST Framework (DRF) |
| Backend package manager | [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`) — not pip/poetry |
| App server | [Granian](https://github.com/emmett-framework/granian) (ASGI) — **not** uvicorn/gunicorn |
| Linting | [Ruff](https://docs.astral.sh/ruff/) (lint only; no formatter opinion enforced yet) |
| Backend tests | pytest + pytest-django, [model_bakery](https://model-bakery.readthedocs.io/) for fixtures, Faker for random data |
| Database | PostgreSQL |
| Media storage | MinIO (S3-compatible), via `django-storages` — wired up ahead of need, no model uses a file field yet |
| Async / background jobs | Celery + Redis (broker & result backend) |
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind CSS + shadcn/ui |
| Frontend package manager | [pnpm](https://pnpm.io/) — not npm/yarn |
| Frontend data layer | [TanStack Query](https://tanstack.com/query) for server-state/caching, [Zod](https://zod.dev/) for schema validation (API response parsing + form input validation) |
| Charting | [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) (MIT) — candlestick/line series with built-in zoom/pan and a real time scale |
| Containerization | Docker + Docker Compose (all services run via `docker compose up`) |
| Theming | Light + dark mode out of the box (shadcn/ui + `next-themes`), minimalist design |

## Architecture principles

### Multi-user ready from day one
No model is single-user. Every user-owned model has an explicit FK to the user model
(`AUTH_USER_MODEL`, see `backend/apps/users`), and every queryset/view scopes data to the
requesting user. There is currently one real user, but the data model must not need to change to
onboard more.

### Centralized, extensible permissions
Permission checks are **never** hardcoded as `is_staff`/`is_superuser` checks scattered across
views. Instead:

- `backend/apps/core/permissions.py` defines a small `PermissionService` (`can(user, action,
  resource)` style API) that maps a user to **roles** (currently backed by Django `Group`s, e.g.
  an "admin" group) and decides what actions a role may perform on a given resource type.
- DRF `permissions.BasePermission` subclasses (e.g. `backend/apps/metrics/permissions.py`) are
  thin adapters that delegate to `PermissionService` — they never encode role logic themselves.
- Adding a new role (e.g. "editor" who can create `MetricType`) means changing `PermissionService`
  only — no view rewrites.
- Not every permission is role-gated through `PermissionService` — plain **ownership** (any
  authenticated user manages their own rows) is a separate, equally valid pattern used where the
  action is personal rather than role-restricted. Both patterns live as DRF permission classes in
  `apps/metrics/permissions.py`; which one applies is called out per resource below.
- The frontend also gates admin-only actions in the UI (via `GET /api/auth/me/`'s `is_admin`
  flag), but that's a UX nicety only — the backend permission is the actual boundary.

Today's rules, all in `apps/metrics/permissions.py`:

| Resource | Read | Create/Edit/Delete |
|---|---|---|
| `MetricType` (`MetricTypePermission`, role-gated via `PermissionService`) | any authenticated user | admins only — it's the shared catalog of what *can* be tracked |
| `MetricEntry` (`MetricEntryPermission`, **ownership**) | own entries; admins see everyone's | any authenticated user, for their own entries; admins may also edit/delete anyone's |
| `MetricThreshold` (`MetricThresholdPermission`, **ownership**) | own thresholds only | any authenticated user, for their own thresholds only (no admin override — thresholds are a personal preference) |
| `FormulaDefinition` (`FormulaDefinitionPermission`, role-gated via `PermissionService`) | admins only | admins only |

The important asymmetry: **defining** a metric type is an admin action (it's shared, global
config), but **logging a reading** against one is something every user does for themselves — so
`MetricEntry` create/edit/delete is ownership-based, not role-gated, even though `MetricType`
stays role-gated. Don't conflate the two when adding new metric-related resources.

### Generalized metrics layer
This is the foundational abstraction for the whole app — **not** hardcoded to specific metric
types (weight, blood sugar, insulin dose, water intake, etc. are all just data).

- **`MetricType`** (admin-defined): `name`, `unit`, `value_type` (`number` / `text` / `boolean` /
  `date`), optional `aggregation` hint (`sum` / `last` / `avg`), `is_computed` (marks a virtual
  metric type whose values are derived via a `FormulaDefinition` rather than logged directly —
  see "Computed metrics" below), `created_by`.
- **`MetricEntry`**: FK to `MetricType`, FK to the owning `User`, `value` (`JSONField` — shape
  depends on `value_type`), optional `context` (`JSONField` — free-form metadata such as
  `{"reason": "post-meal", "injection_site": "abdomen"}`), `recorded_at` timestamp. Never created
  for a computed `MetricType` (enforced in `MetricEntrySerializer.validate`).
- **`MetricThreshold`**: per-user, per-`MetricType` `lower_bound`/`upper_bound` (`FloatField`,
  either independently nullable), one row max per (user, metric type). Powers the "% time in
  range" stat — see "Timeframe aggregation" below.
- New kinds of tracked data should almost always be a new `MetricType` row, not a new Django
  model/migration. Only reach for a dedicated model when the domain has structure that doesn't
  fit "one value + optional metadata at a point in time" (e.g. multi-line finance transactions
  later on).

### Timeframe aggregation (OHLC buckets, summary, time-in-range)
`backend/apps/metrics/aggregation.py` holds all bucketing/statistics logic, deliberately decoupled
from the ORM — it operates on a plain `list[DataPoint]` (timestamp + numeric value), not a
queryset, so the exact same code aggregates both stored `MetricEntry` rows and on-the-fly computed
series (see below).

- **`Timeframe(unit, count)`** — a bucket width, e.g. `Timeframe(HOUR, 4)` = "4 hours". `unit` is
  one of minute/hour/day/week/month/year.
- **`bucketize(points, timeframe, range_start)`** → `list[OHLCBucket]` (`open`/`high`/`low`/
  `close`/`count` per bucket). Minute/hour/day/week buckets are fixed-duration, anchored to
  `range_start`; month/year buckets are calendar-aligned (grouped into N-unit chunks from
  `range_start`'s month/year) since those aren't fixed durations. Empty buckets are omitted, not
  zero-filled — sparse data just yields fewer buckets.
- **`summarize(points)`** → min/max/avg/count across the whole range (not bucketed).
- **`time_in_range_percent(points, lower_bound, upper_bound)`** → entry-count-based percentage
  within `[lower_bound, upper_bound]` (inclusive of whichever bound is set), or `None` if no
  threshold is configured or no points exist. Deliberately simple (not time-weighted/interpolated)
  and kept as its own function precisely so a time-weighted mode can be added later without
  changing the API contract.
- Exposed via `GET /api/metric-types/<id>/aggregate/?timeframe_unit=&timeframe_count=&start=&end=`
  (or `relative_days=` instead of `start`/`end`; defaults to the last 30 days). Returns buckets +
  summary + `time_in_range_percent` (using the requesting user's own `MetricThreshold` for that
  metric type, or `null` if none configured) — all three reuse the same `DataPoint` list, per the
  "aggregate once, derive many stats" rule: don't duplicate range-query logic across summary vs.
  buckets vs. time-in-range.
- Only `number`-valued or computed metric types can be aggregated (`400` otherwise) — charting a
  `text`/`boolean`/`date` metric isn't meaningful. The endpoint is always scoped to the requesting
  user (`apps/metrics/selectors.points_for_metric_type`), regardless of role — dashboards are
  personal, so even admins only ever see their own series here (unlike the `MetricEntry` list
  endpoint, which admins can widen to everyone).

### Computed metrics (formulas)
A computed `MetricType` (`is_computed=True`) has no `MetricEntry` rows. Instead, `FormulaDefinition`
(one row per computed metric type, admin-defined) says which built-in formula to run and which
input `MetricType`s to pull values from — `apps/metrics/formulas.py` does the evaluation:

- **`as_of_value(metric_type_id, user, at)`** — the input's most recent value at or before
  timestamp `at`, for `user`. Missing data yields `None`, never a default/fake value.
- **`evaluate_formula(formula_definition, user, at)`** — resolves every required input via
  `as_of_value` at the same timestamp `at`, then calls the formula's compute function. Returns
  `None` if any input the current branch actually needs (e.g. hip circumference only matters for
  the female branch of `body_fat_navy`) has no value yet.
- **`computed_series(formula_definition, user, range_start, range_end)`** — evaluates the formula
  at every timestamp any of its inputs has an entry at within the range, producing a
  `list[aggregation.DataPoint]`. This is what makes computed metrics chartable over time (e.g. a
  BMI trend), not just a single current-value readout — and it's why they flow through the exact
  same `aggregation.py` pipeline as regular metric types (see `selectors.points_for_metric_type`,
  which branches on `metric_type.is_computed` but converges on the same `DataPoint` shape either
  way). The frontend, dashboard, threshold, and time-in-range code paths never need to know a
  metric type is computed.
- Built-in formulas today: `bmi` (weight_kg, height_cm), `body_fat_navy` (waist_cm, neck_cm,
  height_cm, sex, +hip_cm for the female branch — U.S. Navy method), `tdee_mifflin` (weight_kg,
  height_cm, dob → age derived as-of the evaluation timestamp, sex, activity_level — Mifflin-St
  Jeor). Adding a new formula: register its required variable names in `FORMULA_INPUT_VARS` and a
  compute function in `_FORMULA_COMPUTE`.
- `sex`/`activity_level`/date-of-birth are plain `MetricType`s (text/date), not a bespoke user
  profile system — consistent with "new tracked data is a `MetricType` row, not a new model".

### Backend layering convention (selectors / services)
- **`selectors.py`** (per app, e.g. `backend/apps/metrics/selectors.py`) holds all read-query
  logic. Views/viewsets never build querysets inline in `get_queryset` — they call a selector.
  This is where ownership/visibility rules (e.g. "admins see everyone's entries, everyone else
  sees only their own") live, in one place per resource.
- A `services.py` per app (write-side logic beyond what a serializer's `create`/`update` can
  reasonably hold) will be introduced the first time a feature needs one — none has needed it yet.

### Infrastructure set up ahead of need
Celery + Redis and MinIO are wired up (broker/result backend, worker service, S3-compatible
media storage) starting with the metrics feature even though nothing uses them yet (no Celery
tasks, no file fields), so future features don't require infra work.

## Directory structure

```
life-controller/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml            # uv-managed deps + ruff + pytest config
│   ├── uv.lock
│   ├── manage.py
│   ├── config/                   # Django project package
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── dev.py
│   │   │   └── prod.py
│   │   ├── urls.py
│   │   ├── celery.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── core/                  # shared: PermissionService, base models/mixins
│   │   ├── users/                 # custom User model + session auth endpoints
│   │   │   ├── models.py
│   │   │   ├── serializers.py
│   │   │   ├── views.py           # LoginView / LogoutView / MeView
│   │   │   └── urls.py
│   │   └── metrics/               # MetricType / MetricEntry / MetricThreshold / FormulaDefinition
│   │       ├── models.py
│   │       ├── selectors.py       # all read-query logic for this app
│   │       ├── aggregation.py     # timeframe bucketing / summary / time-in-range (ORM-free)
│   │       ├── formulas.py        # computed-metric evaluation engine (BMI, body fat %, TDEE)
│   │       ├── serializers.py
│   │       ├── views.py
│   │       ├── permissions.py
│   │       ├── admin.py
│   │       └── urls.py
│   └── tests/                     # all backend tests live here, mirroring apps/
│       ├── conftest.py            # fixtures shared across every test package
│       ├── core/
│       ├── users/
│       └── metrics/
│           └── conftest.py        # fixtures shared within tests/metrics/ only
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── app/
    │   ├── layout.tsx              # QueryProvider > ThemeProvider > AuthProvider > NavBar
    │   ├── login/page.tsx
    │   ├── formulas/page.tsx        # FormulaDefinition list + create (admin-only, incl. reads)
    │   └── metrics/
    │       ├── page.tsx             # MetricType list + create (admin-gated)
    │       └── [id]/page.tsx        # dashboard (chart/summary/time-in-range) + entry list/create
    ├── components/
    │   ├── ui/                      # shadcn/ui primitives only
    │   ├── metrics/                 # feature components
    │   │   ├── metric-chart.tsx             # lightweight-charts candlestick/line wrapper
    │   │   ├── metric-dashboard.tsx         # timeframe selector + chart + summary stats
    │   │   ├── threshold-config.tsx         # per-user threshold dialog + useMetricThreshold hook
    │   │   ├── create-formula-definition-dialog.tsx
    │   │   ├── create-metric-entry-dialog.tsx
    │   │   └── create-metric-type-dialog.tsx
    │   ├── auth-provider.tsx        # current-user context, backed by TanStack Query
    │   ├── query-provider.tsx
    │   ├── theme-provider.tsx
    │   └── theme-toggle.tsx
    └── lib/
        ├── api.ts                   # typed API client — parses every response with Zod
        ├── types.ts                 # Zod schemas + inferred TS types
        └── query-keys.ts            # centralized TanStack Query key factories
```

## Running locally

```bash
cp .env.example .env
docker compose up --build
```

This starts: `db` (Postgres), `redis`, `minio` + `minio-init` (bucket bootstrap), `backend`
(Django/DRF served by Granian, auto-reload), `celery-worker`, and `frontend` (Next.js dev server).

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Django admin: http://localhost:8000/admin
- MinIO console: http://localhost:9001

First-time setup (migrations run automatically on backend startup; you still need a user):

```bash
docker compose exec backend python manage.py createsuperuser
```

Backend tests and lint (also runnable outside Docker via `uv run` from `backend/`):

```bash
docker compose exec backend uv run pytest
docker compose exec backend uv run ruff check .
```

Frontend lint/typecheck (from `frontend/`, requires `pnpm install` locally or run inside the
`frontend` container):

```bash
pnpm exec eslint .
pnpm exec tsc --noEmit
```

## Git workflow

- **One feature = one branch.** Never mix unrelated features on one branch.
- Branch naming: `feature/<short-name>`, e.g. `feature/metrics-module`,
  `feature/metric-entry-api`.
- Each branch is a single reviewable unit of work with a clear PR description.
- `CLAUDE.md` is updated in the same commit/PR as the change it documents, not after the fact.

## Current feature status

| Feature | Branch | Status |
|---|---|---|
| Metrics module core (MetricType/MetricEntry backend + centralized permissions + session auth + Docker infra incl. MinIO + frontend CRUD UI with TanStack Query/Zod) | `feature/metrics-module` | Implemented, manually verified end-to-end via browser |
| Dashboards & computed metrics (Lightweight Charts candlestick/line dashboard with timeframe selector, timeframe-aggregation API, per-user `MetricThreshold` + time-in-range stat, `date` value type, computed `MetricType`s via `FormulaDefinition`/`bmi`/`body_fat_navy`/`tdee_mifflin`, admin-only formulas UI) | `feature/metrics-module` | Implemented, manually verified end-to-end via browser (chart in light/dark, timeframe controls, threshold + time-in-range, BMI computed end-to-end from Weight/Height entries, admin-only formulas gating checked both in the UI and directly against the API) |

`MetricEntry` and `MetricThreshold` are **ownership-based**, not admin-gated: any authenticated
user creates/edits/deletes their own entries and thresholds; only `MetricType` definitions and
`FormulaDefinition`s are admin-only. See "Centralized, extensible permissions" above — this was a
correction partway through the dashboards work, since the original all-admin-gated `MetricEntry`
rule made no sense for a personal tracking app once users other than the admin exist.

No other feature modules (nutrition, workouts, finances) have been started yet.
