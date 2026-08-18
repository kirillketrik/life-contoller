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
| `FavoriteMetric` (**ownership** — exposed as actions on `MetricTypeViewSet`, not a separate permission class; see "Favorite metrics" below) | own favorites only | any authenticated user, for their own favorites only |

The important asymmetry: **defining** a metric type is an admin action (it's shared, global
config), but **logging a reading** against one is something every user does for themselves — so
`MetricEntry` create/edit/delete is ownership-based, not role-gated, even though `MetricType`
stays role-gated. Don't conflate the two when adding new metric-related resources.

### Generalized metrics layer
This is the foundational abstraction for the whole app — **not** hardcoded to specific metric
types (weight, blood sugar, insulin dose, water intake, etc. are all just data).

- **`MetricType`** (admin-defined): `name`, `unit`, `value_type` (`number` / `text` / `boolean` /
  `date` / `choice`), optional `aggregation` hint (`sum` / `last` / `avg`), `is_computed` (marks a
  virtual metric type whose values are derived via a `FormulaDefinition` rather than logged
  directly — see "Computed metrics" below), `is_singleton` (marks a metric type that holds one
  fact about the user rather than a time series — e.g. Sex, Date of birth — so a user edits their
  one `MetricEntry` instead of accumulating new ones; enforced server-side in
  `MetricEntrySerializer.validate` on create, same "reject — edit the existing one instead"
  pattern as `MetricThreshold`'s per-user uniqueness check), `created_by`.
- **`MetricTypeChoice`**: the fixed option list for a `choice`-valued `MetricType` (e.g. Sex:
  male/female; Activity Level: sedentary/light/moderate/active/very_active). Each option has a
  stable `code` (what `MetricEntry.value` stores and what formulas compare against — never shown
  to the user), a Russian `label`, and an optional `numeric_value` — set it when the option should
  feed a calculation as a number (Activity Level's TDEE multiplier), leave it null when the option
  is only ever compared by code (Sex, branched on in a formula's `if/then/else`). Created/replaced
  atomically with its `MetricType` via `apps/metrics/services.py` (see "Backend layering
  convention" below) — nested writes on `MetricTypeSerializer`, not a separate endpoint.
- **`MetricEntry`**: FK to `MetricType`, FK to the owning `User`, `value` (`JSONField` — shape
  depends on `value_type`; for `choice` it's the option's `code`, validated against the metric
  type's actual options in `MetricEntrySerializer`), optional `context` (`JSONField` — free-form
  metadata such as `{"reason": "post-meal", "injection_site": "abdomen"}`), `recorded_at`
  timestamp. Never created for a computed `MetricType` (enforced in
  `MetricEntrySerializer.validate`).
- **`MetricThreshold`**: per-user, per-`MetricType` `lower_bound`/`upper_bound` (`FloatField`,
  either independently nullable), one row max per (user, metric type). Powers the "% time in
  range" stat — see "Timeframe aggregation" below.
- New kinds of tracked data should almost always be a new `MetricType` row, not a new Django
  model/migration. Only reach for a dedicated model when the domain has structure that doesn't
  fit "one value + optional metadata at a point in time" (e.g. multi-line finance transactions
  later on).

### Favorite metrics (dashboard)
`FavoriteMetric` is a per-user through-model (`user`, `metric_type`, `order`, unique per
user+metric type) letting a user pin a metric's chart to their dashboard — per-user, not global,
same as `MetricThreshold`; favoriting a metric never affects what other users see.

- Exposed as **actions on `MetricTypeViewSet`** (`apps/metrics/views.py`), not a separate
  viewset/router entry, since favoriting only ever makes sense in the context of a metric type:
  `POST`/`DELETE /api/metric-types/<id>/favorite/` (idempotent toggle), `GET
  /api/metric-types/favorites/` (the current user's favorites, each pre-bucketed with a recent
  series — see below), `PATCH /api/metric-types/favorites/reorder/` (persists a new `order` for
  an exact-match set of the user's own favorite metric-type ids).
- **Ownership, not role-gated**, despite living on `MetricTypeViewSet` (whose CRUD actions *are*
  role-gated via `MetricTypePermission`): `get_permissions()` overrides to plain `IsAuthenticated`
  for the three favorite-related actions, and every query is scoped to `request.user` directly in
  the view — no object-level permission check needed, since a favorite's identity in the URL is
  always the *metric type* id, never the favorite row's own id, so there's no cross-user object to
  leak. Same reasoning as `MetricEntry`/`MetricThreshold`: personal action, not shared config.
- `GET /favorites/` returns each favorite with its metric type plus a pre-bucketed ~30-day daily
  series (`selectors.favorites_chart_data_for_user`, reusing `points_for_metric_type`/`bucketize`/
  `summarize` — same "aggregate once" building blocks as `/aggregate/`) so the dashboard renders
  every favorite chart card from this one response, instead of one `/aggregate/` request per card.
  Works for computed metric types too (BMI, TDEE, ...), same as `/aggregate/`. A favorited
  non-chartable metric type (`text`/`boolean`/`date` — the UI never offers this, but the API
  doesn't block it) degrades to an empty series rather than erroring the whole list.
- **Reordering**: the backend endpoint is implemented and tested, but the frontend doesn't call it
  yet — drag-and-drop reordering was scoped as a nice-to-have, not required for v1 (see
  `frontend/components/metrics/favorite-toggle.tsx`/`app/[locale]/page.tsx`). Favorites currently
  display in `order`/`created_at` order (insertion order, since every new favorite defaults to
  `order=0`). Follow-up if/when it's worth the drag-and-drop UI work.
- Frontend: `useIsFavoriteMetric`/`FavoriteToggleButton` (`components/metrics/favorite-toggle.tsx`)
  is the single place that calls the favorite/unfavorite endpoints — an optimistic local toggle
  (not a cache-level optimistic update, since a newly favorited item has no chart data client-side
  to fabricate) that rolls back on error, matching the "keep favorite-toggling logic in a hook
  layer" convention. Rendered on `MetricDashboard` (metric detail page) and on each
  `FavoriteMetricCard` (dashboard's favorites section, `components/dashboard/favorite-metric-card.tsx`)
  — both read/write the same `FAVORITE_METRICS_QUERY_KEY`, so toggling in either place stays in
  sync. The dashboard favorites section reuses the existing `ChartCard` wrapper (extended with an
  optional `action` slot for the toggle button) and `MetricChart` — no second chart component —
  and caps display at 8 cards, showing a "N of M" note rather than a dedicated favorites page if
  there are more (the metric detail page is still reachable for every metric, favorited or not).

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

### Computed metrics (unified formula engine)
A computed `MetricType` (`is_computed=True`) has no `MetricEntry` rows. Instead, `FormulaDefinition`
(one row per computed metric type, admin-defined) holds an `expression` — a small AST (JSON) —
that `apps/metrics/formula_engine/` parses, validates, and evaluates. There is no more hardcoded
per-formula Python (the old `apps/metrics/formulas.py` + `FormulaDefinition.formula_key`/
`input_mapping` are gone) — BMI, body-fat % (Navy method), and TDEE (Mifflin-St Jeor) are now
ordinary seeded `FormulaDefinition` rows on this same engine, same as any admin-authored formula.

**Why an AST, not a string expression evaluated via `eval`**: a raw string is the right *mental*
model for a formula but the wrong *storage* model — injection risk, and no structural guarantee
the thing even parses. The builder UI (below) composes the tree visually; the stored JSON is
parsed by a strict recursive validator (`formula_engine.nodes.parse_node`) before it's ever
evaluated.

- **`formula_engine/nodes.py`** — the node types (`metric`, `constant`, `binary_op` for `+ - * /
  ^`, `unary_op` for `sqrt abs neg`, `function` for `min max round age log10`, `comparison` for
  `== != < > <= >=`, `conditional` for `if/then/else`) and `parse_node`, a strict parser that
  rejects unknown node types/ops/arity. `age` and `log10` are engine additions beyond the
  builder's basic palette (sqrt/abs/round): `age(dob_metric)` generalizes the old
  `formulas.py` dob-special-case (TDEE needs age-from-date-of-birth, and there's no named-variable
  system anymore to special-case around), `log10` is required to reproduce the Navy body-fat %
  formula's logarithms.
- **`formula_engine/interpreter.py`** — `evaluate_node(node, resolver)`, a recursive
  isinstance-dispatch visitor (the architecture policy's "visitor pattern" home case: interpreting
  an AST). Division by zero and any unresolved (`None`) input propagate as `None` at every step —
  never raises, never substitutes a default, same rule as before this engine existed.
- **`formula_engine/resolvers.py`** — `AsOfResolver(user, at)` resolves a `metric` leaf: for a
  non-computed metric type, the most-recent `MetricEntry.value` at/before `at` (choice-valued
  metrics resolve to their option's `numeric_value` if set, else its `code` — this is what lets
  Activity Level resolve as a number and Sex resolve as a comparable string, with no extra AST
  concept needed); for a computed metric type, recursively evaluates *its own* `FormulaDefinition`
  at the same `at` (cycle-guarded), which is how formulas can depend on other formulas.
- **`formula_engine/validation.py`** — `validate_expression(expression, computed_metric_type_id)`,
  called from `FormulaDefinitionSerializer.validate` and the preview endpoint: structural parse,
  every `metric` leaf's id must reference an existing `MetricType` (`missing_metric_type` — this
  is the full extent of "missing dependency" validation: a formula may be saved before anyone has
  logged data for its inputs, live preview just shows no value yet for that case), a literal `x /
  0` anywhere in the tree (`division_by_zero`), and a circular-reference check across the
  transitive metric-type dependency graph (`circular_reference`). Returns stable error `code`s
  (not prose) so the frontend maps each one to Russian copy independently.
- **`formula_engine/series.py`** — `evaluate_formula`/`computed_series`, the same public contract
  `apps/metrics/selectors.points_for_metric_type` already called on the old module (only the
  import path changed): `computed_series` finds the transitive closure of **base** (non-computed)
  metric types a formula depends on, evaluates at every timestamp any of them has an entry at, and
  drops `None`s — this is what makes computed metrics chartable over time, not just a
  single-current-value readout, through the exact same `aggregation.py` pipeline as regular
  metric types.
- **`formula_engine/builtins.py`** — pure functions building the BMI/body-fat-navy/TDEE-Mifflin
  expression dicts from metric-type ids, shared by `seed_metrics.py` (fresh installs) and the
  `0007_migrate_formula_expressions_data` migration (which converted every pre-engine
  `FormulaDefinition` row using the same builders).
- `POST /api/formula-definitions/preview/` (`FormulaPreviewView`, admin-only like the rest of
  formula editing) validates and, if structurally valid, evaluates a **not-yet-saved** expression
  for the requesting admin's own current data — one endpoint powers both the builder's live
  preview and "reject with a clear error before saving".
- `sex`/`activity_level`/date-of-birth are plain `MetricType`s (`choice`/`choice`/`date`), not a
  bespoke user profile system — consistent with "new tracked data is a `MetricType` row, not a new
  model".

**Builder UI** (`frontend/components/metrics/formula-builder/`, replaces the old
`create-formula-definition-dialog.tsx`): a drag-and-drop canvas (`@dnd-kit/core`) with a metrics
palette (searchable, draggable chips) and an operators palette (arithmetic or comparison chips
depending on context, plus click-to-apply √/abs/round wraps, grouping, and if/then/else). Working
representation is `frontend/lib/formula-builder/tokens.ts`'s `FlatToken[]` — a flat, linear chip
sequence per canvas level, easier to render/constrain than the tree directly — compiled to the
`FormulaNode` AST (`compileToAst`, precedence-climbing, `null` if incomplete) only at the API
boundary. Editing is **drill-in**: adding a group/function-wrap/conditional inserts an empty
container and immediately focuses into it (breadcrumb navigation moves back out), rather than a
free-form "select a range of chips and wrap them" interaction. **Scope for this pass**: create
only, like the rest of the formulas UI before it (no edit-in-builder / AST→FlatToken decompile
built yet — a reasonable named follow-up, not a half-finished feature); the palette exposes
arithmetic ops + √/abs/round + grouping + if/then/else, not the engine's full `min`/`max`/`log10`/
`age` (those remain reachable by hand-authoring an `expression`, e.g. via Django admin, same as
how the built-in formulas use them). Read-only Russian rendering of an already-saved formula (the
formulas list page) is `frontend/lib/formula-builder/render-node.ts`'s
`renderFormulaNodeRussian` — walks the tree directly (not through `FlatToken`) and always
parenthesizes nested `binary_op`/`comparison` children, trading a few redundant parens for a
guarantee the displayed formula can never be misread with the wrong operator precedence.

### Backend layering convention (selectors / services)
- **`selectors.py`** (per app, e.g. `backend/apps/metrics/selectors.py`) holds all read-query
  logic. Views/viewsets never build querysets inline in `get_queryset` — they call a selector.
  This is where ownership/visibility rules (e.g. "admins see everyone's entries, everyone else
  sees only their own") live, in one place per resource.
- A `services.py` per app (write-side logic beyond what a serializer's `create`/`update` can
  reasonably hold) is introduced the first time a feature needs one — `apps/metrics/services.py`
  is the first: `create_metric_type_with_choices`/`update_metric_type_choices` wrap the
  `MetricType` + `MetricTypeChoice` nested write in a transaction, called from
  `MetricTypeSerializer.create`/`update` rather than doing the nested-write logic inline.

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

Decisions made during the choice-metrics/unit-localization/formula-engine work
(`feature/formula-engine`):

- **AST JSON over a string expression + `eval`**, for `FormulaDefinition.expression` — see
  "Computed metrics" above. The builder UI's `FlatToken[]` working representation is a deliberate
  second, simpler shape (flat per canvas level, not the tree) that only compiles to the real AST
  at the API boundary, rather than making the UI manipulate the tree directly.
- **`@dnd-kit/core` + `@dnd-kit/sortable` + `@dnd-kit/utilities`** added as the formula builder's
  drag-and-drop layer — accessible (keyboard sensor works out of the box, confirmed via manual
  testing) and far less custom drag-state code than hand-rolled HTML5 DnD would have needed.
- **Choice-metric options (`MetricTypeChoice`) resolve to `numeric_value` if set, else `code`**,
  with no separate AST concept for "this leaf is numeric" vs. "this leaf is a comparable code" —
  the formula engine just always tries `numeric_value` first. This is why Activity Level (every
  option has a multiplier) drops straight into TDEE's arithmetic and Sex (no option has one)
  drops straight into an `if/then/else` condition, using the exact same `metric` leaf node either
  way.
- **Unit localization was a data migration, not just a `seed_metrics.py` change** — existing dev
  data already had `MetricType.unit = "kcal"` rows, so `0005_seed_choice_options_data` also
  updates the TDEE type's unit to `"ккал"` in place (alongside converting Sex/Activity Level to
  `choice`), and `seed_metrics.py` was updated to match for fresh installs.
- **Read-only Russian rendering of a saved formula always parenthesizes nested binary/comparison
  operations** (`render-node.ts`) rather than only when operator precedence requires it — the
  first version omitted this and rendered BMI's `weight / (height/100)^2` as the flat, misleading
  `Вес ÷ Рост ÷ 100 ^ 2`; always-parenthesizing trades a few redundant parens for a guarantee it
  can never be misread.
- **`MetricType.is_singleton`** (migration `0009_metrictype_is_singleton`, bundling the schema
  `AddField` with a `RunPython` data backfill in one file, same shape as `0005`'s data migration)
  fixes a UX gap: Sex/Date of birth are one-time facts, not a time series, so letting a user
  repeatedly "add" entries for them was confusing and left stale rows a formula could pick up by
  `recorded_at` accident. Enforcement lives in `MetricEntrySerializer.validate` (reject a second
  create for the same user+metric type, same "edit the existing one instead" error shape as
  `MetricThresholdSerializer`'s per-user uniqueness check) — deliberately not a DB `UniqueConstraint`
  like `MetricThreshold`'s, since existing pre-flag data could already contain duplicates and a
  constraint would break the migration; the serializer check is sufficient since it's the only
  write path. `seed_metrics.py` sets it via `SINGLETON_METRIC_KEYS = {"dob", "sex"}` in each
  type's `defaults=` (fresh installs only — `get_or_create` defaults don't touch already-existing
  rows, hence the migration's data backfill for pre-existing dev/prod data). Activity Level stays
  non-singleton on purpose: unlike Sex/DOB it's a state that can legitimately change over time.
- **`MetricEntryDialog`** (`frontend/components/metrics/metric-entry-dialog.tsx`, replaces the old
  create-only `create-metric-entry-dialog.tsx`) does both create and edit from one component — pass
  an optional `entry` prop and it switches which mutation (`metricEntries.create` vs. the new
  `metricEntries.update`) runs on submit, re-seeding its value-type-branched form state from `entry`
  on open (same "seed from the source of truth when opened" pattern as `ThresholdConfigDialog`).
  This is also what makes the singleton UX work with no separate code path: the entry list page
  passes `entry={entries[0]}` instead of `undefined` when `metricType.is_singleton` is true, which
  flips the top-of-page button from "log a value" to "edit the value" once one exists. Per-row edit
  uses the same component with a custom icon-button `trigger` prop. `DeleteMetricEntryButton`
  (`delete-metric-entry-button.tsx`) is the new `alert-dialog` shadcn primitive's first use in this
  app — added via `pnpm dlx shadcn add alert-dialog` — for the destructive-delete confirm, matching
  the "confirm before an irreversible action" pattern rather than a bare `window.confirm`.
- **`SidebarInset` (`components/ui/sidebar.tsx`) needs `min-w-0` alongside its `flex flex-1`** —
  without it, a flex item's minimum width defaults to its content's intrinsic width (the classic
  flexbox min-width bug), so a wide, unwrapped table cell (e.g. a long rendered formula expression
  on the formulas list) forced the *entire* page — including the top header bar with the sidebar
  trigger and theme toggle — wider than the viewport, pushing right-aligned header/page-action
  buttons off-screen. `Table`'s own `overflow-x-auto` wrapper (`components/ui/table.tsx`) only
  works if every flex ancestor between it and the viewport can actually shrink to the available
  width; `min-w-0` is what lets it. Also gave the formulas table's formula-expression cell
  `whitespace-normal break-words max-w-[36rem]` so it wraps instead of relying on horizontal
  scroll for the common case. Any future flex-column content area added under `SidebarInset` that
  can contain wide unwrapped content (a table, a code block) should not need its own `min-w-0` fix
  now that the ancestor chain allows shrinking — but wide content should still get its own
  `overflow-x-auto` scroll container rather than assuming the page will handle it.

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
│   │   └── metrics/               # MetricType(+Choice) / MetricEntry / MetricThreshold / FormulaDefinition / FavoriteMetric
│   │       ├── models.py
│   │       ├── selectors.py       # all read-query logic for this app
│   │       ├── services.py        # write-side logic beyond a serializer's create/update (nested MetricType+choices writes)
│   │       ├── aggregation.py     # timeframe bucketing / summary / time-in-range (ORM-free)
│   │       ├── formula_engine/    # AST-based formula engine — nodes/interpreter/resolvers/validation/series/builtins
│   │       ├── serializers.py
│   │       ├── views.py
│   │       ├── permissions.py
│   │       ├── admin.py
│   │       ├── urls.py
│   │       └── management/commands/
│   │           └── seed_metrics.py    # idempotent baseline MetricTypes (incl. choice options) + FormulaDefinitions
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
    │       ├── formulas/
    │       │   ├── page.tsx           # FormulaDefinition list, Russian-rendered (admin-only, incl. reads)
    │       │   └── builder/page.tsx   # drag-and-drop formula builder (create-only, see "Computed metrics")
    │       └── metrics/
    │           ├── page.tsx           # MetricType list + create (admin-gated)
    │           └── [id]/page.tsx      # dashboard (chart/summary/time-in-range) + entry list/create/edit/delete
    ├── components/
    │   ├── ui/                      # shadcn/ui primitives only
    │   ├── layout/
    │   │   └── app-sidebar.tsx      # fixed sidebar: nav groups, admin gating, user footer menu
    │   ├── dashboard/
    │   │   ├── chart-card.tsx              # icon+title Card wrapper used by every dashboard card
    │   │   ├── favorite-metric-card.tsx    # ChartCard + MetricChart for one favorited metric
    │   │   ├── horizontal-bar-list.tsx     # categorical breakdowns (no time axis — not a chart lib)
    │   │   └── monthly-trend-chart.tsx     # lightweight-charts area series for the 12-month trend
    │   ├── metrics/                 # feature components
    │   │   ├── metric-chart.tsx             # lightweight-charts candlestick/line wrapper
    │   │   ├── metric-dashboard.tsx         # timeframe selector + chart + summary stats
    │   │   ├── threshold-config.tsx         # per-user threshold dialog + useMetricThreshold hook
    │   │   ├── favorite-toggle.tsx          # star toggle button + useIsFavoriteMetric hook
    │   │   ├── metric-entry-dialog.tsx      # create AND edit (pass `entry`) — one form, value-type branching
    │   │   ├── delete-metric-entry-button.tsx     # icon button + AlertDialog confirm, per entry row
    │   │   ├── create-metric-type-dialog.tsx      # incl. the choice-option row editor and is_singleton switch
    │   │   └── formula-builder/             # canvas/palettes/preview + use-formula-builder.ts state hook
    │   ├── auth-provider.tsx        # current-user context, backed by TanStack Query
    │   ├── query-provider.tsx
    │   ├── theme-provider.tsx
    │   └── theme-toggle.tsx
    └── lib/
        ├── api.ts                   # typed API client — parses every response with Zod
        ├── types.ts                 # Zod schemas + inferred TS types (incl. the FormulaNode AST schema)
        ├── query-keys.ts            # centralized TanStack Query key factories
        └── formula-builder/         # tokens.ts (FlatToken model + compile), render-node.ts (read-only AST render)
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

Seed baseline `MetricType`s/`FormulaDefinition`s (height, sex + activity level as `choice` types
with their options, neck/waist/hip circumference, date of birth, weight, plus the
`bmi`/`body_fat_navy`/`tdee_mifflin` `FormulaDefinition`s wired to them on the AST formula engine
— see `apps/metrics/management/commands/seed_metrics.py`). Idempotent (matches on
`MetricType.name`/`MetricTypeChoice.code`), safe to re-run:

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
| Favorite metric charts on the dashboard (`FavoriteMetric` per-user through-model; favorite/unfavorite/list/reorder actions on `MetricTypeViewSet`, ownership-scoped; dashboard "Избранное" section reusing `ChartCard`+`MetricChart`, capped at 8 with a "N of M" note; star toggle on the metric detail page and every favorite card, optimistic with rollback) | `feature/favorite-metrics` | Implemented, manually verified end-to-end via browser as two different users (favorite/unfavorite/idempotency, per-user scoping — one user's favorites and chart data never show another's, computed-metric-type favoriting via BMI/TDEE, toggle state in sync between the detail page and dashboard card); backend: 111/111 tests passing incl. 15 new for favorites, `ruff check .` clean; frontend: `eslint`/`tsc` clean. Reorder endpoint is implemented+tested but not yet wired to any frontend drag-and-drop UI — noted as a follow-up above. |
| Choice-type metrics (`MetricType.value_type="choice"` + `MetricTypeChoice`, Sex/Activity Level converted to it), unit localization (`kcal`→`ккал`), and a unified AST formula engine (`apps/metrics/formula_engine/` replaces hardcoded per-formula Python; BMI/body-fat/TDEE reseeded as ordinary `FormulaDefinition` rows) with a drag-and-drop visual builder (`@dnd-kit`, create-only) incl. live preview and save-time validation (missing metric type / division by zero / circular reference); `MetricType.is_singleton` for one-time-fact metric types (Sex, Date of birth) with create-time enforcement and a UI that swaps "add" for "edit" once a value exists; `MetricEntry` edit/delete wired into the entry list UI (`MetricEntryDialog` create+edit, `DeleteMetricEntryButton` with an `alert-dialog` confirm) — the backend `ModelViewSet` already supported PATCH/DELETE, only the frontend was missing it | `feature/formula-engine` | Implemented, manually verified end-to-end via browser (choice metric type + option creation, choice-select entry logging, drag-and-drop formula build with live preview computing a real value, save + Russian-rendered display on the formulas list, precedence-correct parenthesization, singleton metric type hides "add" in favor of "edit" once a value exists and rejects a second entry via the API, per-row edit/delete with delete confirmation); backend: 143/143 tests passing incl. new singleton-enforcement tests, `ruff check .` clean on every file this pass touched (18 pre-existing `E501` line-length errors in untouched `tests/metrics/test_thresholds.py`/`test_permissions.py` predate this branch); frontend: `eslint`/`tsc` clean |

`MetricEntry` and `MetricThreshold` are **ownership-based**, not admin-gated: any authenticated
user creates/edits/deletes their own entries and thresholds; only `MetricType` definitions and
`FormulaDefinition`s are admin-only. See "Centralized, extensible permissions" above — this was a
correction partway through the dashboards work, since the original all-admin-gated `MetricEntry`
rule made no sense for a personal tracking app once users other than the admin exist.

No other feature modules (nutrition, workouts, finances) have been started yet.
