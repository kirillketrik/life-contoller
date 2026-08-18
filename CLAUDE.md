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
| Frontend package manager | [pnpm](https://pnpm.io/) — not npm/yarn. **Run all pnpm/shadcn commands through the frontend Docker container** (`docker compose exec frontend pnpm ...`) — Node/pnpm aren't on the host `PATH`, and the container's `node_modules` is a separate named volume from any host install |
| Frontend data layer | [TanStack Query](https://tanstack.com/query) for server-state/caching, [Zod](https://zod.dev/) for schema validation (API response parsing + form input validation) |
| Charting | [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) (MIT) for time-series (candlestick/line/area) — **not** used for categorical breakdowns, see "Architectural decisions" |
| Typography | [Geist Variable](https://fontsource.org/fonts/geist) via `@fontsource-variable/geist` — global font, wired in `app/[locale]/layout.tsx` + `app/globals.css` |
| Localization | [next-intl](https://next-intl.dev/) — Russian (`ru`) is the default and only locale today; see "Architectural decisions" for the routing setup |
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

## Skills policy

- Before starting any UI work, check for and use a project skill dedicated to
  professional UI/UX creation (sidebar/nav patterns, dashboard card layout,
  typography via Geist Variable, spacing, and Russian-first copy). If no such
  skill exists yet, create one after this redesign and keep it updated as the
  UI evolves.
- Before starting any architecture/design work, check for and use a project
  skill that documents this project's architecture decisions and the design
  patterns in use (service layer, repository, factory, strategy, etc.). If no
  such skill exists yet, create one and keep it updated as the architecture
  evolves.
- Whenever a development task is repeated (or is likely to recur) — e.g.
  scaffolding a new CRUD resource, adding a new chart card, adding a new
  metric type, adding a new localized page — extract it into a reusable skill
  instead of redoing the work manually each time.
- Default UI language is Russian; all new UI copy must ship in Russian first.
- Global font is Geist Variable (`@fontsource-variable/geist`); do not
  introduce other fonts without updating this policy.
- Follow Next.js App Router best practices on the frontend and Django/DRF
  best practices on the backend for all new code.

These four project skills implement the policy today: `.claude/skills/ui-design/SKILL.md`
(sidebar/dashboard/typography/copy patterns), `.claude/skills/architecture/SKILL.md` (the
decisions and patterns below, in skill form), `.claude/skills/crud-resource/SKILL.md` (scaffolding
checklist), and `.claude/skills/dashboard-chart-card/SKILL.md` (adding a dashboard card). Keep
them updated in the same commit as a change that affects what they document.

## Architectural decisions

Decisions made during the sidebar/dashboard/i18n redesign (`feature/ui-redesign-i18n`) that
aren't obvious from the code alone:

- **Sidebar built on shadcn's `Sidebar` primitive, not hand-rolled.** It already implements the
  collapsible-group / icon+label / active-highlight / mobile-offcanvas structure the redesign
  needed (`components/ui/sidebar.tsx`, installed via `pnpm dlx shadcn add sidebar collapsible
  avatar separator tooltip sheet`) — reinventing it would have duplicated non-trivial
  accessibility/state-management work for no benefit.
- **Chart library split**: Lightweight Charts (time-scale) is used only for genuinely time-series
  dashboard data (`components/dashboard/monthly-trend-chart.tsx`); categorical breakdowns
  (`components/dashboard/horizontal-bar-list.tsx`) use plain Tailwind bars instead of forcing a
  time-axis library to fake a categorical one, or adding a second charting dependency for one
  simple visual. See the `dashboard-chart-card` skill.
- **`GET /api/dashboard-summary/`** follows the same "aggregate once, derive many stats" shape as
  `/aggregate/`: one selector function (`selectors.dashboard_summary_for_user`), one thin
  `APIView`, a raw dict response — deliberately **no** new output-serializer class, matching
  `/aggregate/`'s existing convention rather than introducing a new one.
- **i18n routing**: `next-intl` with `locales: ["ru"]`, `defaultLocale: "ru"`,
  `localePrefix: "as-needed"` — Russian stays unprefixed (`/metrics`), so adding a second locale
  later is additive (append to `locales`, add `messages/en.json`) rather than a URL-breaking
  change. All routes live under `app/[locale]/...`, and `app/[locale]/layout.tsx` is the *only*
  layout — there's no separate `app/layout.tsx` above it, since Next's root-layout requirement is
  satisfied by the outermost layout already being under `[locale]` (every route lives under that
  segment).
- **`middleware.ts` → `proxy.ts`**: Next.js 16 deprecated the `middleware.ts` file convention in
  favor of `proxy.ts` (same `next-intl` `createMiddleware(routing)` export). This repo uses
  `proxy.ts` — don't reintroduce a `middleware.ts`.
- **No repository/service layer added for the redesign.** The one new backend endpoint
  (dashboard-summary) fit the existing selectors convention; nothing in this pass needed
  multi-model transactional writes or swappable data sources, so `services.py` wasn't introduced
  (see "Backend layering convention" above — it's added the first time a feature actually needs
  it, not preemptively).
- **Known tooling quirk, not a code bug**: in dev mode, Turbopack can write a corrupted
  `.next/dev/types/validator.ts` for the `[locale]` root layout (a duplicated, torn validation
  block) that breaks a plain `tsc --noEmit`. Verified via `docker compose stop frontend &&
  docker compose run --rm frontend sh -c "rm -f .next/dev/types/validator.ts && pnpm exec tsc
  --noEmit"` that the actual project code has zero type errors — the corruption is isolated to
  that one generated file. If `tsc` reports an error only in that file, it's this, not a regression.
- **`backend/pyproject.toml`'s `[tool.ruff] exclude`** was fixed to `extend-exclude` — plain
  `exclude` replaces Ruff's default excludes (including `.venv`) instead of adding to them, which
  made `ruff check .` scan the entire virtualenv. Always use `extend-exclude` for project-specific
  exclusions, never `exclude`, unless you deliberately want to lose the defaults.
- **`backend/docker-entrypoint.sh`** must stay LF-terminated (enforced via `.gitattributes`) — CRLF
  line endings from a Windows checkout make `sh` inside the Linux container fail to parse `set -e`,
  crashing the backend container on startup.

## Directory structure

```
life-controller/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── .gitattributes                # forces LF on *.sh (see "Architectural decisions")
├── .claude/
│   └── skills/                   # ui-design, architecture, crud-resource, dashboard-chart-card
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
│   │       ├── urls.py
│   │       └── management/commands/
│   │           └── seed_metrics.py    # idempotent baseline MetricTypes + FormulaDefinitions
│   └── tests/                     # all backend tests live here, mirroring apps/
│       ├── conftest.py            # fixtures shared across every test package
│       ├── core/
│       ├── users/
│       └── metrics/
│           └── conftest.py        # fixtures shared within tests/metrics/ only
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── proxy.ts                     # next-intl createMiddleware(routing) — Next 16's renamed "middleware"
    ├── i18n/
    │   ├── routing.ts                # defineRouting: locales, defaultLocale, localePrefix
    │   ├── request.ts                # getRequestConfig — loads messages/<locale>.json
    │   └── navigation.ts             # locale-aware Link/usePathname/useRouter (createNavigation)
    ├── messages/
    │   └── ru.json                   # all UI copy, namespaced per page/component
    ├── app/
    │   ├── favicon.ico
    │   ├── globals.css                # design tokens + --font-sans (Geist Variable)
    │   └── [locale]/
    │       ├── layout.tsx             # the only layout — html/body, providers, AppSidebar shell
    │       ├── page.tsx               # dashboard: KPI row + chart-card grid
    │       ├── login/page.tsx
    │       ├── formulas/page.tsx      # FormulaDefinition list + create (admin-only, incl. reads)
    │       └── metrics/
    │           ├── page.tsx           # MetricType list + create (admin-gated)
    │           └── [id]/page.tsx      # dashboard (chart/summary/time-in-range) + entry list/create
    ├── components/
    │   ├── ui/                      # shadcn/ui primitives only
    │   ├── layout/
    │   │   └── app-sidebar.tsx      # fixed sidebar: nav groups, admin gating, user footer menu
    │   ├── dashboard/
    │   │   ├── chart-card.tsx              # icon+title Card wrapper used by every dashboard card
    │   │   ├── horizontal-bar-list.tsx     # categorical breakdowns (no time axis — not a chart lib)
    │   │   └── monthly-trend-chart.tsx     # lightweight-charts area series for the 12-month trend
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

Seed baseline `MetricType`s/`FormulaDefinition`s (height, sex, activity level, neck/waist/hip
circumference, date of birth, weight, plus the `bmi`/`body_fat_navy`/`tdee_mifflin`
`FormulaDefinition`s wired to them — see `apps/metrics/management/commands/seed_metrics.py`).
Idempotent (matches on `MetricType.name`), safe to re-run:

```bash
docker compose exec backend python manage.py seed_metrics
```

Backend tests and lint (also runnable outside Docker via `uv run` from `backend/`):

```bash
docker compose exec backend uv run pytest
docker compose exec backend uv run ruff check .
```

Frontend lint/typecheck (run through the `frontend` container — Node/pnpm aren't on the host
`PATH`, and the container's `node_modules` is a separate named Docker volume from any host
install):

```bash
docker compose exec frontend pnpm exec eslint .
docker compose exec frontend pnpm exec tsc --noEmit
```

Installing a new package or shadcn component works the same way, e.g.
`docker compose exec frontend pnpm add <package>` or
`docker compose exec frontend pnpm dlx shadcn add <component>`.

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
| UI redesign, localization & DX (fixed sidebar with collapsible nav + user footer menu; dashboard landing page with KPI cards + chart-card grid via new `GET /api/dashboard-summary/`; Geist Variable global font; Russian-first `next-intl` localization across every page/component incl. shadcn primitives; 4 project skills — `ui-design`/`architecture`/`crud-resource`/`dashboard-chart-card`) | `feature/ui-redesign-i18n` (branched off `main`, which was created from `feature/metrics-module`'s tip) | Implemented, manually verified end-to-end via browser (Russian copy on every page, sidebar collapse/expand + active-item highlight + admin-group gating, metric-type create flow, dashboard KPI/chart cards with real data, light/dark theme); backend: 96/96 tests passing incl. 4 new for `dashboard-summary`, `ruff check .` clean after fixing a pre-existing exclude-config bug; frontend: `eslint`/`tsc` clean |

`MetricEntry` and `MetricThreshold` are **ownership-based**, not admin-gated: any authenticated
user creates/edits/deletes their own entries and thresholds; only `MetricType` definitions and
`FormulaDefinition`s are admin-only. See "Centralized, extensible permissions" above — this was a
correction partway through the dashboards work, since the original all-admin-gated `MetricEntry`
rule made no sense for a personal tracking app once users other than the admin exist.

No other feature modules (nutrition, workouts, finances) have been started yet.
