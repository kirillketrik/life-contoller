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
| `MetricEntry` (`MetricEntryPermission`, **ownership**) | own entries only (no admin override — same as thresholds) | any authenticated user, for their own entries only (no admin override) |
| `MetricThreshold` (`MetricThresholdPermission`, **ownership**) | own thresholds only | any authenticated user, for their own thresholds only (no admin override — thresholds are a personal preference) |
| `FormulaDefinition` (`FormulaDefinitionPermission`, role-gated via `PermissionService`) | admins only | admins only |
| `DashboardElement` (**ownership** — exposed as actions on `MetricTypeViewSet`, not a separate permission class; see "Dashboard elements" below) | own dashboard elements only | any authenticated user, for their own dashboard elements only |
| `MetricImportSettings` / bulk import (**ownership** — exposed as actions on `MetricTypeViewSet`; see "Bulk metric-entry import" below) | own saved template only | any authenticated user, for their own data — bulk import is just repeated `MetricEntry` creation |
| `NutrientType` (`apps/nutrition/permissions.py`'s `NutrientTypePermission`, role-gated via `PermissionService`, same pattern as `MetricType`) | any authenticated user | admins only — shared micronutrient catalog |
| `FoodItem` (`FoodItemPermission`, **ownership**) | own food items only | any authenticated user, for their own food items only (no admin override) |
| `Recipe` (`RecipePermission`, **ownership**) | own recipes only | any authenticated user, for their own recipes only (no admin override) |
| `MealEntry` (`MealEntryPermission`, **ownership**) | own logged meals only | any authenticated user, for their own logged meals only (no admin override) |

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

### Dashboard elements
`DashboardElement` is a per-user, per-metric-type through-model (`user`, `metric_type`, six
`show_chart`/`show_current`/`show_max`/`show_min`/`show_avg`/`show_time_in_range` booleans,
`timeframe`, `custom_range_start`/`custom_range_end`, `order`, unique per user+metric type) letting
a user choose which elements — chart, and/or current/max/min/avg/time-in-range — to show for a
metric on their dashboard, and over what timeframe, all configured together as one row/block
rather than a boolean favorite. Replaces the earlier boolean `FavoriteMetric` entirely (migration
`0011` converts any pre-existing favorite into `show_chart=True, timeframe="all"`, carrying over
`order`) — per-user, not global, same as `MetricThreshold`; configuring a metric's dashboard
elements never affects what other users see. `show_time_in_range` was added in migration `0012`,
after the other five (`0011`), following the same "one new `show_*` boolean, default `False`"
shape — no data migration needed since it defaults off for every existing row.

- **Timeframe governs both the chart's visible range and what feeds max/min/avg** — the same
  resolved range, not two separate settings. `current` is deliberately exempt: always the single
  latest recorded entry, never filtered by `timeframe`, even if that entry falls outside the
  selected range (`selectors.current_value_for_metric_type`). `timeframe` reuses the exact same
  6-preset vocabulary as the metric detail page's existing chart control (`7d`/`30d`/`90d`/`1y`/
  `3y`/`all` — `aggregation.NAMED_RANGE_PRESETS`, mirroring frontend `RANGE_PRESETS` 1:1) plus a
  `custom` option (`custom_range_start`/`custom_range_end`) — deliberately not a second,
  incompatible timeframe representation. `aggregation.resolve_named_range(key, at=, custom_start=,
  custom_end=)` resolves a key into a concrete `(range_start, range_end, bucket)` tuple; a custom
  range picks its bucket granularity by span using the same breakpoints the fixed presets encode.
- Works for computed metric types (BMI, TDEE, ...) with **no special-casing**: `current` evaluates
  the formula at "now" (`formula_engine.evaluate_formula`), and chart/max/min/avg reuse
  `points_for_metric_type` exactly like a regular metric type. This is also why max/min/avg stay
  **Python-side** via the existing ORM-free `aggregation.summarize()` rather than a DB-side
  `.aggregate()` — a computed metric's series only exists as Python-evaluated points, never DB
  rows, so a DB-aggregation path would need a second code path for computed metrics, defeating the
  "same code either way" rule the rest of this layer follows.
- **Exposed as an action on `MetricTypeViewSet`** (`apps/metrics/views.py`) for the per-metric
  config, same "personal action lives as an action on this viewset" pattern as the old favorites:
  `POST`/`PATCH /api/metric-types/<id>/dashboard-element/` (upsert — create on first save, update
  on every save after; returns the saved config plus its resolved stats), `DELETE` (idempotent
  removal — a no-op, not an error, when none exists). Two **top-level** endpoints (not
  `MetricTypeViewSet` actions, since they span every configured metric type, not one):
  `GET /api/dashboard-elements/` (every configured element for the requesting user, each with its
  resolved stats — one request for the whole dashboard, not one `/aggregate/`-style request per
  block) and `PATCH /api/dashboard-elements/reorder/` (persists a new `order` for an exact-match
  set of the user's own dashboard-element metric-type ids, same validate-then-reassign shape the
  old favorites reorder endpoint had).
- **At least one `show_*` flag is required to save** (`DashboardElementInputSerializer.validate`,
  same "at least one" rule as `MetricThresholdSerializer`'s bounds check) — disabling every element
  is not an implicit side effect of saving an all-false row; the DELETE method above is the only
  way to remove a metric from the dashboard. `timeframe="custom"` requires both range dates set,
  with start not after end.
- **Time-in-range is a dashboard element like max/min/avg, computed the same way**:
  `selectors.dashboard_element_stats` fetches the requesting user's `MetricThreshold` for the
  metric type (same selector `GET /aggregate/` already used) whenever `show_chart` or
  `show_time_in_range` is set, and calls the existing `aggregation.time_in_range_percent` over the
  same resolved-range `points` used for max/min/avg — no separate query path. `null` when
  `show_time_in_range` is on but no threshold is configured (mirrors `MetricEntry`/`points`: a flag
  can be enabled before there's data to back it, same "show a `—` tile rather than hide it" choice
  as the other four elements).
- **The chart draws the threshold's bounds as red dashed price lines**, not just the time-in-range
  percentage: both `GET /aggregate/` and `dashboard_element_stats` include a `threshold`
  (`{lower_bound, upper_bound}` or `null`) field alongside `points`, resolved from the same
  `MetricThreshold` fetch above — reused rather than a second request, per the "aggregate once,
  derive many stats" rule. `MetricChart` (`frontend/components/metrics/metric-chart.tsx`) draws
  each non-null bound via `series.createPriceLine({..., lineStyle: LineStyle.Dashed})` in a
  `--destructive`-adjacent red (`#dc2626` light / `#f87171` dark) — a price line, not a second
  series, since the bound isn't part of the plotted data. Reuses the `threshold` i18n namespace's
  `lowerBound`/`upperBound` labels (`ThresholdConfigDialog`'s own field labels) as each line's
  title rather than introducing duplicate copy.
- **Ownership, not role-gated**, despite living on `MetricTypeViewSet` (whose CRUD actions *are*
  role-gated via `MetricTypePermission`): `get_permissions()` overrides to plain `IsAuthenticated`
  for the `dashboard_element` action, and every query is scoped to `request.user` directly in the
  view/selectors — no object-level permission check needed, since a config's identity in the URL
  is always the *metric type* id, never the row's own id. Same reasoning as
  `MetricEntry`/`MetricThreshold`: personal action, not shared config.
- `selectors.dashboard_element_stats`/`dashboard_element_data`/`dashboard_elements_data_for_user`
  are the one place this resolution logic lives, called both by the batched list endpoint (looped,
  one call per element) and by the single-metric write action (to return the freshly saved
  element's stats) — "one aggregation function, called per-metric there and in a loop here," not
  duplicated. `GET /aggregate/` (the metric detail page's existing chart endpoint) also gained a
  `current` field via the same `current_value_for_metric_type` selector, rather than a new,
  largely-overlapping `/stats/`-style endpoint — the detail page's timeframe control already drove
  everything else this needed (chart/summary/time-in-range/period-changes) through that one call.
- Frontend: `useDashboardElementConfig`/`DashboardElementConfigDialog`
  (`components/metrics/dashboard-element-config.tsx`) is the single place that reads/writes a
  metric's dashboard config — the hook derives the current config from the batched
  `DASHBOARD_ELEMENTS_QUERY_KEY` list query (same "derive from the list, no dedicated GET-by-id
  endpoint" approach the old `useIsFavoriteMetric` used), and the dialog is a `Switch`-per-element
  picker (matching the `is_computed`/`is_singleton` toggle pattern already used on
  `create-metric-type-dialog.tsx`) plus a timeframe `Select` with an added "Свой диапазон" (custom)
  option and, only then, two `type="date"` inputs. A destructive-confirm `AlertDialog` guards the
  "Убрать с дашборда" (remove) action, matching `DeleteMetricEntryButton`'s confirm-before-delete
  pattern. Rendered as a trigger button next to the title on `MetricDashboard` (metric detail
  page) — configuration only ever happens from a metric's own detail page, never from the
  dashboard itself. `components/dashboard/dashboard-element-card.tsx`'s `DashboardElementCard` is
  the read-only dashboard block: reuses the existing `ChartCard` wrapper and `MetricChart`, shows
  only the enabled among current/max/min/avg via a new shared `components/metrics/summary-stat.tsx`
  (extracted so the detail page's own stat tiles and every dashboard block render identically), and
  its `action` slot is a small gear-icon link back to the metric's detail page (no inline timeframe
  control on the dashboard block itself — timeframe is configured on the detail page only, per the
  model above). Dashboard caps display at 8 blocks with a "N of M" note, same convention as before.
  **Known Base UI quirk**: a shadcn `Button` combined with `render={<Link .../>}` needs
  `nativeButton={false}` explicitly — without it, Base UI logs a console warning (and degrades
  semantics) because it expects `render`'s output to be an actual `<button>` element, not an `<a>`.
- **Period-change badges**: unchanged in shape from before — `PeriodChangeBadges`
  (`components/metrics/period-change-badges.tsx`) still renders the 24h/7d/30d/3m/1y `%` change via
  `--success`/`--destructive` tokens, shown in `ChartCard`'s `titleExtra` slot for each dashboard
  block and next to the `<h1>` on the metric detail page, backed by the same
  `selectors.period_changes_for_metric_type`. Included in both `GET /aggregate/`'s and
  `GET /dashboard-elements/`'s response bodies as `period_changes`.

### Bulk metric-entry import
Lets a user paste or upload many `MetricEntry` rows at once for a single metric type, using a
positional **template-builder** pattern adapted from a prior project (`kirillketrik/accounting`'s
bulk-asset-create page) rather than a CSV-header column-mapper: pasted/uploaded text is one record
per line, split positionally into `{value}` and `{date}` tokens by a user-built
`{field1}{separator}{field2}` template — no header row, no per-column mapping UI.

- **Target metric selection** excludes computed (`is_computed`) and singleton (`is_singleton`)
  metric types — both are enforced again server-side (`400`) even though the picker never offers
  them, same defense-in-depth as `/aggregate/`'s value-type check.
- **`MetricImportSettings`** (`user`, `metric_type`, `template`, `separator`, `date_format`,
  `decimal_separator`, unique per user+metric type) is the "set as default" template a user saves
  per metric type — **not** one flat per-user setting like the reference implementation had,
  because different metric types have meaningfully different import shapes worth reusing (a fixed
  "date;value" export for one metric, "value date" pasted from somewhere else for another).
  Exposed as an ownership-scoped `GET`/`PUT /api/metric-types/<id>/import-settings/` action pair on
  `MetricTypeViewSet` (same "personal action lives as an action on this viewset" pattern as
  dashboard elements) — `GET` returns `null` rather than `404` when unset, so the frontend always gets a
  200 and just checks for `null` to decide whether to pre-fill the builder or start empty.
- **Client/server parsing split**: `frontend/lib/metric-bulk-parse.ts` (`parseImportTemplate`,
  `parseImportText`) only does the positional *splitting* — template validation (separator
  required, known fields only, no duplicates, `{value}` must be present) and turning each line into
  raw `{value, date}` string tokens. The actual value *parsing* — numeric (respecting
  `decimal_separator`), choice code/label matching (case-insensitive against the metric type's
  actual `MetricTypeChoice` rows), boolean/text/date-typed values, and `{date}` parsing via the
  configured `date_format` — happens server-side in `apps/metrics/services.py`'s
  `resolve_bulk_import_items`, the single function shared by both endpoints below (mirrors the
  reference's "one parsing path for preview and create").
- **`resolve_bulk_import_items`** classifies every row as `new` / `duplicate_skip` /
  `duplicate_overwrite` / `invalid` (an `error_code`, not prose, same "stable code the frontend maps
  to copy" convention as the formula engine's validation errors) — a row's fate already reflects the
  run's chosen `duplicate_policy`, so preview and create can never disagree about what a row will
  do. Duplicate detection compares `recorded_at`'s **date** (not exact timestamp) against the
  user's existing entries for that metric type — a row whose template has no `{date}` field at all
  (a valid, if unusual, template) always resolves to `new`, since there's nothing to compare against.
  A resolved `decimal_separator=","` row only strips `.` as a thousands separator when the raw value
  actually contains a `,` — a plain `"70.5"` is left untouched rather than mangled into `"705"`,
  since treating every `.` as a thousands separator regardless of context silently corrupts an
  already-unambiguous number.
- **`execute_bulk_import`** (also `services.py`) persists a resolved batch: `new` rows are created,
  `duplicate_overwrite` rows update the existing entry's `value` in place (same row id, not a
  delete+recreate), `duplicate_skip`/`invalid` rows are left untouched — partial success, a bad or
  duplicate row never blocks the rest of the batch, same rule as the reference's bulk-asset-create.
- Two `MetricTypeViewSet` actions, both ownership-scoped (`IsAuthenticated`, queries scoped to
  `request.user`) via the same `get_permissions()` override that already carves out the
  dashboard-element action: `POST /api/metric-types/<id>/import/preview/` resolves and returns per-row status
  without persisting; `POST /api/metric-types/<id>/import/` resolves *and* persists, returning
  `created_count`/`updated_count`/`skipped_count`/`invalid_count` plus the same per-item list.
  Both take the same body shape (`items`, `date_format`, `decimal_separator`, `duplicate_policy`).
- **Frontend**: `components/shared/template-builder.tsx`/`separator-field.tsx` are the ported,
  domain-agnostic versions of the reference's components — generic over a `TField extends string`
  field union (here `"value" | "date"`) rather than hardcoded to metric-import fields, so a future
  bulk-import-shaped feature reuses them instead of copy-pasting. `components/metrics/bulk-import/`
  (`bulk-import.tsx` + `use-bulk-import.ts` hook + `preview-table.tsx`) follows the
  `formula-builder`-style split of state/derivation (the hook) from presentation (the components) —
  the hook owns the selected metric type, the form state (seeded from the saved
  `MetricImportSettings` the moment it's fetched, via React's "adjust state during render" pattern
  rather than a `useEffect` `setState`, per this project's lint rules), and the client-side parsed
  rows. The page (`app/[locale]/metrics/import/page.tsx`) supports paste, `.csv` upload, and `.txt`
  upload — all three just fill the same textarea via `FileReader`, there's no separate CSV-specific
  code path, matching the "no header parsing, one raw-text field" scope decision above. An
  "advanced mode" switch swaps the `TemplateBuilder` buttons for a raw text input bound to the same
  template string, for hand-authoring a template the button UI can't express (matching the formula
  builder's "advanced" affordances elsewhere in this app).
- **Known DRF quirk**: `CharField`'s default `trim_whitespace=True` reduces a space-only
  `separator` (a common, meaningful separator value) to `""` and then rejects it as blank —
  `MetricImportSettingsSerializer.separator` and `BulkImportRequestSerializer.date_format`
  explicitly set `trim_whitespace=False` to avoid this. Any other free-text field that could
  legitimately be pure whitespace needs the same override; a `ModelSerializer`'s auto-generated
  `CharField` for such a model field won't have it by default.
- **The `{date}` token's time-of-day is optional** — `date_format` may include time directives
  (`%H`/`%I`/`%M`/`%S`/`%p`), in which case `services._parse_bulk_date` uses the parsed time as-is;
  when it doesn't, the current time of day is substituted instead of midnight, so a plain date-only
  template (the common case) doesn't silently backdate every imported entry to `00:00`. Detection
  is a regex over `date_format` itself (`_TIME_DIRECTIVE_RE`), not the parsed value, since a
  format without a time directive can never produce a non-midnight `strptime` result to test
  against. The date component stays required either way — only the time half is optional. A raw
  time with no timezone info is interpreted in Django's `current_tz` (`TIME_ZONE = "UTC"`), the
  same reference frame the no-time fallback's `timezone.now()` already uses — consistent within
  bulk import, but distinct from `MetricEntryDialog`'s single-entry form, which resolves the
  browser's own local timezone via `datetime-local` + `toISOString()`.

### Timeframe aggregation (raw point series, summary, time-in-range)
`backend/apps/metrics/aggregation.py` holds all statistics logic, deliberately decoupled from the
ORM — it operates on a plain `list[DataPoint]` (timestamp + numeric value), not a queryset, so the
exact same code aggregates both stored `MetricEntry` rows and on-the-fly computed series (see
below).

- **Charts always plot every raw point in the range, never an aggregated/bucketed value** — a
  product decision, not just a rendering default: an earlier version grouped points into OHLC
  buckets (`bucketize`/`OHLCBucket`, still present in `aggregation.py` and covered by its own unit
  tests in `test_aggregation.py`, but no longer called from `views.py`/`selectors.py`) and rendered
  candlesticks when a bucket had real spread. Both `GET /aggregate/` and `dashboard_element_stats`
  now return a flat `points` list (`{"timestamp", "value"}` per entry, chronological) instead of
  `buckets` — a 1-year chart shows every individual entry logged that year, not one dot per week.
  `timeframe_unit`/`timeframe_count` are still accepted/echoed (and `resolve_named_range` still
  picks a nominal bucket granularity per preset) purely as a UI hint for whether the chart's x-axis
  shows time-of-day (`MetricChart`'s `timeVisible`), not for aggregating the series itself.
- **`summarize(points)`** → min/max/avg/count across the whole range (not bucketed) — unaffected by
  the above, already worked over raw points.
- **`time_in_range_percent(points, lower_bound, upper_bound)`** → entry-count-based percentage
  within `[lower_bound, upper_bound]` (inclusive of whichever bound is set), or `None` if no
  threshold is configured or no points exist. Deliberately simple (not time-weighted/interpolated)
  and kept as its own function precisely so a time-weighted mode can be added later without
  changing the API contract.
- Exposed via `GET /api/metric-types/<id>/aggregate/?timeframe_unit=&timeframe_count=&start=&end=`
  (or `relative_days=` instead of `start`/`end`; defaults to the last 30 days). Returns the raw
  `points` series + summary + `time_in_range_percent` (using the requesting user's own
  `MetricThreshold` for that metric type, or `null` if none configured) — all three reuse the same
  `DataPoint` list, per the "aggregate once, derive many stats" rule: don't duplicate range-query
  logic across summary vs. the chart series vs. time-in-range.
- Only `number`-valued or computed metric types can be aggregated (`400` otherwise) — charting a
  `text`/`boolean`/`date` metric isn't meaningful. The endpoint is always scoped to the requesting
  user (`apps/metrics/selectors.points_for_metric_type`), regardless of role — dashboards are
  personal, so even admins only ever see their own series here. `MetricEntry` listing
  (`selectors.metric_entry_list_for_user`) is scoped the same way now — no admin override — so
  this is no longer a special case relative to the entry list, just the same ownership rule
  applied in two places (see "Centralized, extensible permissions" above).
- **`MetricChart`** (`frontend/components/metrics/metric-chart.tsx`) always renders a
  `lightweight-charts` `LineSeries` — no candlestick branch. It deduplicates points that land on
  the same whole second (lightweight-charts requires strictly increasing unique timestamps),
  keeping the later value, same "last write wins" spirit as the old bucket `close`.

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

### Nutrition module (`apps/nutrition`)
A separate Django app from `apps.metrics` — food tracking has its own domain shape (a food item
is a multi-field record with fixed macro columns, not a single timestamped value), so it doesn't
fit the generalized metrics layer directly, but it deliberately reuses that layer's *patterns*:
selectors/serializers/permissions layering, the two permission patterns (role-gated vs.
ownership), and the "nested nested-model write goes through `services.py`, not the serializer"
rule. Building incrementally, phase by phase, one branch per phase; this pass is **Phase 1 (food
item core)** only — recipes, meal logging, meal planning, and the Open Food Facts integration are
later phases, not yet built.

- **`NutrientType`** (admin-defined, role-gated exactly like `MetricType` — see the permissions
  table above): `name`, `unit`, `category` (`macro` / `micro`), `is_system` (marks the
  `seed_nutrients`-seeded baseline vs. an admin-added one later; informational only, doesn't affect
  permissions). This is the micronutrient equivalent of `MetricType` — new nutrients (Vitamin C,
  Iron, Fiber, ...) are new rows here, never new `FoodItem` columns, so the catalog is extensible
  without a migration, same "generic over hardcoded fields" rule as the metrics layer.
- **`FoodItem`** — **ownership-based, not a shared catalog** (the key difference from
  `MetricType`/`NutrientType`): every authenticated user creates/edits/deletes their own food
  items, scoped by `owner`, with no admin override — two users logging "chicken breast" may mean
  different brands/prep, so there's no single canonical row to share. Calories/protein/fat/carbs
  are fixed `DecimalField` columns (always needed, fast to read) rather than going through
  `NutrientType`/`FoodNutrientValue` like every other nutrient — this is the one deliberate
  exception to "generic over hardcoded fields," made because these four are universal to every
  food item and worth the fast, always-present columns. `source` (`own`/`external`),
  `external_id`, and `is_verified` exist on the model now (per the original phase plan) but are
  **read-only through the API in this phase** — manually adding/editing a food item always
  produces an `own`, verified row; only the not-yet-built Open Food Facts search phase will
  actually write `external`/unverified items, server-side, on selection. Search
  (`GET /api/food-items/?search=`) filters by name via the `(owner, name)` index, for the
  eventual meal-logging food picker.
- **`FoodNutrientValue`** — the join model (`food_item`, `nutrient_type`, `amount_per_100g`) that
  lets a food item carry arbitrary micronutrient data with no schema change, same role
  `MetricTypeChoice` plays for choice metrics. Written as a nested list on `FoodItemSerializer`
  (`nutrient_values`), replaced atomically with its `FoodItem` via
  `apps/nutrition/services.py`'s `create_food_item_with_nutrients`/`update_food_item_nutrients` —
  same "nested multi-model write goes through `services.py`, called from the serializer's
  `create`/`update`" pattern as `MetricType`+`MetricTypeChoice`. A `UniqueConstraint` on
  (`food_item`, `nutrient_type`) plus a serializer-level `validate_nutrient_values` check reject a
  food item that sets the same nutrient twice.
- `management/commands/seed_nutrients.py` seeds a baseline catalog (fiber, sugar, saturated fat,
  trans fat, cholesterol, sodium as `category=macro` — sub-macro breakdown nutrients, not one of
  the four fixed `FoodItem` columns but still part of the macronutrient picture; the common
  vitamins/minerals as `category=micro`) as `is_system=True` rows, idempotent like `seed_metrics`.
- Frontend: `components/nutrition/food-item-dialog.tsx`'s `FoodItemDialog` does both create and
  edit from one component (pass an optional `item` prop), same pattern as `MetricEntryDialog` —
  including a `nutrient_values` row editor (nutrient `Select` + amount input, add/remove rows) that
  mirrors `create-metric-type-dialog.tsx`'s choice-option row editor. Macro/amount inputs are
  `type="text"` + `inputMode="decimal"` accepting either `.` or `,`, same known browser-locale
  workaround as every other numeric input in this app (see the `feature/formula-engine`
  architectural-decisions note below). `app/[locale]/nutrition/page.tsx` is the list/search page
  (own `Input`-driven `search` query param, no debounce — small enough dataset that it wasn't
  worth adding yet); `components/nutrition/delete-food-item-button.tsx` mirrors
  `delete-metric-entry-button.tsx`'s `AlertDialog`-confirm pattern exactly. Sidebar gained its own
  top-level "Питание" (Nutrition) group (`components/layout/app-sidebar.tsx`) — not nested under
  "Метрики," since it's a sibling domain per the project overview, not a metrics feature.
- **Test fixture note**: `other_user` (a second plain user for ownership/scoping tests) moved from
  `tests/metrics/conftest.py` to the shared root `tests/conftest.py` once `tests/nutrition` needed
  it too — see the `crud-resource` skill's "only put something here once two or more test packages
  want it" rule; this is the first time that threshold was actually crossed.

**Phase 2 (meal logging)**, added on top of Phase 1:

- **`MealEntry`** — ownership-based like `FoodItem`: `owner`, `datetime`, `meal_type`
  (`breakfast`/`lunch`/`dinner`/`snack`), `food_item` (required `PROTECT` FK — `recipe` isn't
  wired up yet; Phase 4 adds `Recipe` and the `CheckConstraint` requiring exactly one of
  `food_item`/`recipe`), `quantity_g`, `cost` (nullable, unused placeholder per the original
  model spec — Phase 6 is what actually surfaces it as a real input; the field already exists so
  that phase is additive, not a migration). `MealEntrySerializer.validate` rejects logging against
  another user's `FoodItem` and a non-positive `quantity_g`. Per-entry `calories`/`protein`/`fat`/
  `carbs` are `SerializerMethodField`s computed from `food_item`'s per-100g values × `quantity_g`
  — never stored, so they can't drift from the food item they reference (same "computed property,
  not a duplicated value" rule the original prompt calls out for `Recipe`/`MealEntry` totals).
  `GET /api/meal-entries/?date=YYYY-MM-DD` narrows to one day, for the food-diary view.
- **Daily totals are exposed through the existing formula-metric engine by *materializing* them
  as ordinary `MetricEntry` rows**, not by extending the engine with a new "sum of X on this day"
  node type. `apps/nutrition/services.recompute_daily_nutrition_metrics(user, entry_date)` sums
  that day's `MealEntry` rows into calories/protein/fat/carbs and upserts one `MetricEntry` per
  macro (looked up by name via `DAILY_METRIC_NAMES`, at noon local time for that date) on four
  ordinary, non-computed `MetricType`s ("Калории (день)"/"Белки (день)"/"Жиры (день)"/"Углеводы
  (день)", seeded by `apps/nutrition/management/commands/seed_nutrition_metrics.py`). Deletes the
  materialized entry instead of writing an explicit `0` when a day ends up with no meals left — "no
  data that day" and "logged zero" are different things. Called from `MealEntryViewSet.perform_
  create`/`perform_update`/`perform_destroy` for every date touched (both the old and new date on
  an update that moves an entry to a different day); skips silently if a daily-total `MetricType`
  hasn't been seeded yet, same tolerance the formula engine already has for a formula referencing
  a metric type nobody has logged data for. **Why materialize instead of a new engine node type**:
  once the totals are ordinary `MetricEntry` rows, every existing metrics feature — charts,
  timeframes, dashboard elements, thresholds — works completely unmodified; verified end-to-end via
  browser (a materialized "Калории (день)" entry rendered correctly on both the metric detail page
  and, once a dashboard element was configured for it through the existing, unmodified
  `DashboardElementConfigDialog`, on the dashboard itself).
- **"% of daily caloric target" is one more ordinary computed `MetricType`+`FormulaDefinition`** —
  `seed_nutrition_metrics` also seeds "% дневной нормы калорий" =
  `calories_day / tdee_mifflin * 100` (a plain `/` and `*`, `builtins.metric`/`binop` — no new
  formula-engine capability needed), satisfying the "daily intake should be comparable against
  [caloric needs], the same way threshold metrics report % time in range" design decision with
  zero engine changes. Only seeded if the TDEE metric type (from `seed_metrics`) already exists —
  run `seed_metrics` before `seed_nutrition_metrics` for it to be created; otherwise re-running
  `seed_nutrition_metrics` later picks it up once TDEE exists.
- **Known limitation, not yet solved**: the four daily-total `MetricType`s are ordinary (not
  `is_computed`) so `recompute_daily_nutrition_metrics` can write `MetricEntry` rows into them
  directly — but that also means nothing stops a user from manually logging their own entry against
  one via `MetricEntryDialog`/the API (`is_computed=True` was considered and rejected: the metrics
  selector layer branches on it to read from a `FormulaDefinition` instead of stored entries, which
  is incompatible with reading materialized data). A manual entry would just get overwritten the
  next time that day's meals are edited, so this self-heals rather than silently corrupting data,
  but it's a real gap worth closing with a proper "system-managed, no manual entries" concept if it
  ever causes real confusion.
- Frontend: `components/nutrition/meal-entry-dialog.tsx`'s `MealEntryDialog` — create-and-edit in
  one component (pass an optional `entry`), same pattern as `MetricEntryDialog`/`FoodItemDialog`,
  plus a `defaultDate` prop so "log a meal" from the food-diary page seeds the datetime to noon of
  whatever day is currently selected rather than always defaulting to now.
  `components/nutrition/delete-meal-entry-button.tsx` mirrors `delete-food-item-button.tsx` exactly.
  `app/[locale]/nutrition/log/page.tsx` (sidebar: "Дневник питания", above "Продукты") is the food
  diary — a date picker (defaults to today) driving `GET /api/meal-entries/?date=`, four
  `SummaryStat` tiles (reused from `components/metrics/summary-stat.tsx`) summing the visible day's
  entries **client-side** (deliberately not a server endpoint — the day's entries are already
  fetched for the table, and summing four numbers client-side isn't worth a second request), and a
  table of that day's entries with inline edit/delete.
- **Dev-tooling note from this pass**: Base UI `Select`/`Switch` components in this app need a full
  synthetic `pointerdown`/`mousedown`/`pointerup`/`mouseup`/`click` event sequence to open/toggle
  under this session's automation tooling — a bare `.click()` or a single synthetic `click` event
  leaves them inert (already documented for `Select` popovers in the period-change-badges pass
  above; confirmed here to apply to `Switch` too). Not a code issue — real user interaction and
  Playwright/Selenium-style dispatch both work fine; it's specific to how this tooling synthesizes
  events.

**Phase 4 (Recipes)**, added on top of Phase 2 (this phase branched directly off Phase 2, before
Phase 3's Open Food Facts integration was merged — the two are independent slices of the nutrition
module and don't depend on each other):

- **`Recipe`**/**`RecipeIngredient`** — a recipe is a named, ownership-scoped (same as `FoodItem`)
  "union of products": a `Recipe` row (`name`, `servings` — how many servings the *whole* recipe
  yields, `cost`) plus one `RecipeIngredient` row per `FoodItem` it contains (`food_item`,
  `quantity_g`), written as a nested list on `RecipeSerializer` (`ingredients`) and replaced
  atomically via `apps.nutrition.services.create_recipe_with_ingredients`/
  `update_recipe_ingredients` — same "nested multi-model write goes through `services.py`" pattern
  as `FoodItem`+`FoodNutrientValue`. `RecipeIngredient.food_item` is `on_delete=PROTECT`, same
  protection `MealEntry.food_item` already has: a food item in active use can't be silently deleted
  out from under whatever references it. A recipe's ingredients must all be the owner's own food
  items (`RecipeSerializer.validate_ingredients`, mirroring `MealEntrySerializer`'s food-item
  ownership check) — the FK itself doesn't scope by user, so this is what actually stops one user
  referencing another's `FoodItem` by guessing its id.
- **Nutrient totals are never stored, only computed** — `apps.nutrition.selectors` gained
  `food_item_macro_totals(food_item, quantity_g)` (the one place the "per-100g × quantity/100"
  arithmetic lives now, previously duplicated inline in `MealEntrySerializer`),
  `recipe_macro_totals(recipe)` (sums every ingredient's macros — whole-recipe totals) and
  `recipe_macro_totals_per_serving(recipe)` (divides by `Recipe.servings`). `RecipeSerializer`
  exposes both as flat `total_calories`/`total_protein`/`total_fat`/`total_carbs` and
  `calories_per_serving`/`protein_per_serving`/`fat_per_serving`/`carbs_per_serving` fields (8
  `SerializerMethodField`s calling the selector independently) — safe from N+1 because
  `recipe_macro_totals` iterates `recipe.ingredients.all()` (never `.select_related()`/`.filter()`
  chained fresh), and `selectors.recipe_list_for_user` prefetches `ingredients__food_item`, so
  Django's prefetch cache — which only a bare `.all()` reuses — absorbs all 8 calls into the one
  query the list/detail view already made.
- **`MealEntry` now logs either a `FoodItem` or a `Recipe`**, never both — `food_item` and
  `quantity_g` became nullable, a new nullable `recipe` FK (`on_delete=PROTECT`, same reasoning)
  and nullable `servings` DecimalField were added (migration `0003`, generated then applied, not
  hand-written — existing rows already satisfy the new rule since they all have `food_item` set and
  `recipe` null), and a `mealentry_exactly_one_of_food_or_recipe` `CheckConstraint` enforces it at
  the DB level. `MealEntrySerializer.validate` mirrors the same rule at the API level (defense in
  depth, same pattern used everywhere else in this app) and additionally requires `quantity_g > 0`
  for a food-item entry or `servings > 0` for a recipe entry. A recipe-based entry's servings mean
  "how many of the recipe's own servings were eaten" — independent of how many the recipe happens
  to be divided into, so logging `servings=1.5` against a 4-serving recipe means one and a half of
  *those* servings, not 1.5 out of some other total.
- **`selectors.meal_entry_macro_totals(meal_entry)`** is the one function that turns either kind of
  entry into calories/protein/fat/carbs — a food-item entry uses `food_item_macro_totals` directly;
  a recipe entry uses `recipe_macro_totals_per_serving(recipe) × meal_entry.servings`. Both
  `MealEntrySerializer` (per-entry calories shown in the API/diary) and
  `services.recompute_daily_nutrition_metrics` (the Phase 2 daily-total materialization) call this
  same function, so a day's total is correct whether its entries log a `FoodItem` directly, a
  `Recipe`, or a mix of both — **zero special-casing** needed in the materialization logic itself,
  matching the "aggregate once, derive many stats" rule the metrics layer already follows.
  `selectors.meal_entry_list_for_user` prefetches `recipe__ingredients__food_item` for the same
  N+1-avoidance reason as the recipe list.
- **`GET/POST/PATCH/DELETE /api/recipes/`** (`RecipeViewSet`, ownership-scoped via a new
  `RecipePermission`, same plain-ownership pattern as `FoodItemPermission`/`MealEntryPermission`)
  incl. `?search=` by name, mirroring `/api/food-items/` exactly.
- **Known limitation, not yet solved**: editing a recipe's ingredients does *not* retroactively
  recompute the materialized daily-total `MetricEntry` rows for every past day that recipe was
  logged against — only creating/editing/deleting the `MealEntry` itself triggers a recompute. A
  recipe edit's effect on historical days self-heals the next time that day's meals are touched,
  same "self-heals rather than silently corrupting data" tolerance already documented for the
  daily-total metric types' own manual-entry gap in Phase 2 — deliberately not solved eagerly here
  (would need tracking every date a recipe was ever logged against) since it's the same accepted
  class of staleness, not a new one.
- Frontend: `components/nutrition/recipe-dialog.tsx`'s `RecipeDialog` — create-and-edit in one
  component (pass an optional `recipe`), same pattern as `FoodItemDialog`'s nutrient-value row
  editor but for ingredients (food-item `Select` + quantity input, add/remove rows, duplicate food
  items disabled in the picker as a UX guard even though the backend doesn't enforce uniqueness on
  `RecipeIngredient`). Additionally shows a **live, client-side-computed** estimated total calorie
  count while building the recipe (same per-100g × quantity/100 arithmetic as the backend, run
  against the already-fetched food-item list) — purely a UX aid before the recipe is ever saved, not
  a substitute for the server-computed totals shown after saving.
  `components/nutrition/delete-recipe-button.tsx` mirrors `delete-food-item-button.tsx` exactly.
  `app/[locale]/nutrition/recipes/page.tsx` (sidebar: "Рецепты", below "Продукты") is the recipe
  list/search page, same shape as `/nutrition`'s food-item list but showing servings and
  calories-per-serving instead of per-100g macros. `MealEntryDialog` gained an `itemType`
  (`foodItem`/`recipe`) `Select` at the top that swaps the rest of the form: the food-item picker +
  quantity(g) input for `foodItem`, a recipe picker + servings input for `recipe` — derived from
  whether an edited `entry.recipe` is set, so editing an existing recipe-based entry reopens
  correctly pre-selected in recipe mode. The food-diary table (`/nutrition/log`) shows
  `entry.food_item_name ?? entry.recipe_name` with a "рецепт" `Badge` next to a recipe-based row's
  name, and its quantity column shows `{quantity_g} г` or `× {servings}` depending on which is set.
- Manually verified end-to-end via browser: created a 2-serving recipe from two food items (chicken
  200g + rice 100g), confirming the dialog's live estimate (460 kcal) matched the saved totals
  exactly and `calories_per_serving` correctly divided by `servings` (230); logged a meal against
  that recipe via `MealEntryDialog`'s recipe mode, confirming the diary row's badge/servings display
  and its calories (230, i.e. 1 serving eaten) were correct; confirmed the materialized "Калории
  (день)" `MetricEntry` picked up the recipe-based entry's total with no special handling; reopened
  the logged entry's edit dialog and confirmed it correctly restored recipe mode with the right
  recipe pre-selected. Hit both documented dev-loop quirks mid-session (a stale Granian reload
  crash-looping on an `ImportError` for the new `Recipe` model, and stale Turbopack routing 404ing
  the new `/nutrition/recipes` page) — restarting the respective container fixed each, per the
  existing documented workaround.

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
- **Backend dev-loop note, mirrors the frontend Turbopack one below**: Granian's `--reload` file
  watcher can also silently stop picking up edits mid-session (observed while building the
  period-change badges: `selectors.py`/`views.py`/`aggregation.py` edits landed on disk but kept
  serving the pre-edit response, with no error in `docker compose logs backend` and no further
  "Changes detected, reloading workers.." lines). `docker compose restart backend` fixed it. If an
  endpoint keeps returning stale-looking data despite the source clearly having changed, try this
  before assuming the code is wrong.
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
- **Known browser-locale quirk**: the `number`-valued field's `Input` is `type="text"` +
  `inputMode="decimal"`, not `type="number"` — a native `type="number"` input's accepted decimal
  separator follows the browser/OS locale, and under a Russian locale that's a comma, so typing
  `4.4` was silently rejected (only the integer part landed). The text input accepts either `.` or
  `,`; submit normalizes by replacing `,` with `.` before `Number(...)`. Any other free-typed
  numeric field in this app has the same latent bug if it uses `type="number"`.
- **`SidebarInset` (`components/ui/sidebar.tsx`) needs `min-w-0` alongside its `flex flex-1`** —
  without it, a flex item's minimum width defaults to its content's intrinsic width (the classic
  flexbox min-width bug), so a wide, unwrapped table cell (e.g. a long rendered formula expression
  on the formulas list) forced the *entire* page — including the top header bar with the sidebar
  trigger and theme toggle — wider than the viewport, pushing right-aligned header/page-action
  buttons off-screen. `Table`'s own `overflow-x-auto` wrapper (`components/ui/table.tsx`) only
  works if every flex ancestor between it and the viewport can actually shrink to the available
  width; `min-w-0` is what lets it. Any future flex-column content area added under `SidebarInset`
  that can contain wide unwrapped content (a table, a code block) should not need its own
  `min-w-0` fix now that the ancestor chain allows shrinking — but wide content should still get
  its own `overflow-x-auto` scroll container (or truncation, see below) rather than assuming the
  page will handle it.
- **Formulas list's formula-expression cell truncates instead of wrapping**
  (`app/[locale]/formulas/page.tsx`) — the earlier `whitespace-normal break-words max-w-[36rem]`
  fix kept the column from forcing page overflow, but a long formula still bloated every row's
  height. It's now a single-line `truncate` cell (capped `max-w-[28rem]`) rendered as a button;
  clicking it opens a `Dialog` showing the computed metric type name and the full, wrapped formula
  text. Prefer this "truncate + click-to-expand dialog" pattern over wrapping for any other
  table cell that can hold long, unpredictable-length content.

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
│   │   ├── metrics/               # MetricType(+Choice) / MetricEntry / MetricThreshold / FormulaDefinition / DashboardElement / MetricImportSettings
│   │   │   ├── models.py
│   │   │   ├── selectors.py       # all read-query logic for this app
│   │   │   ├── services.py        # write-side logic beyond a serializer's create/update (nested MetricType+choices writes)
│   │   │   ├── aggregation.py     # summary / time-in-range / named ranges (ORM-free); bucketize() unused by app code, kept for its own tests
│   │   │   ├── formula_engine/    # AST-based formula engine — nodes/interpreter/resolvers/validation/series/builtins
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── permissions.py
│   │   │   ├── admin.py
│   │   │   ├── urls.py
│   │   │   └── management/commands/
│   │   │       └── seed_metrics.py    # idempotent baseline MetricTypes (incl. choice options) + FormulaDefinitions
│   │   └── nutrition/              # NutrientType / FoodItem / FoodNutrientValue / MealEntry / Recipe (Phases 1-2, 4 — see "Nutrition module")
│   │       ├── models.py
│   │       ├── selectors.py       # incl. food_item/recipe/meal_entry_macro_totals (Phase 4)
│   │       ├── services.py        # nested FoodItem+FoodNutrientValue and Recipe+RecipeIngredient writes; recompute_daily_nutrition_metrics
│   │       ├── serializers.py
│   │       ├── views.py
│   │       ├── permissions.py
│   │       ├── admin.py
│   │       ├── urls.py
│   │       └── management/commands/
│   │           ├── seed_nutrients.py           # idempotent baseline NutrientType catalog
│   │           └── seed_nutrition_metrics.py   # daily-total MetricTypes + %-of-TDEE FormulaDefinition
│   └── tests/                     # all backend tests live here, mirroring apps/
│       ├── conftest.py            # fixtures shared across every test package (incl. other_user)
│       ├── core/
│       ├── users/
│       ├── nutrition/
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
    │       ├── metrics/
    │       │   ├── page.tsx           # MetricType list + create (admin-gated)
    │       │   ├── [id]/page.tsx      # dashboard (chart/summary/time-in-range) + entry list/create/edit/delete
    │       │   └── import/page.tsx    # bulk metric-entry import (template builder + paste/upload + preview)
    │       └── nutrition/
    │           ├── page.tsx           # FoodItem list + search + create/edit/delete (ownership-gated, Phase 1)
    │           ├── log/page.tsx       # food diary: date picker + daily totals + meal entry list (Phase 2)
    │           └── recipes/page.tsx   # Recipe list + search + create/edit/delete (ownership-gated, Phase 4)
    ├── components/
    │   ├── ui/                      # shadcn/ui primitives only
    │   ├── shared/                  # domain-agnostic reusable widgets (not shadcn primitives)
    │   │   ├── template-builder.tsx        # generic positional-template builder (field toggles + reorder)
    │   │   └── separator-field.tsx         # separator picker with presets + custom-character input
    │   ├── layout/
    │   │   └── app-sidebar.tsx      # fixed sidebar: nav groups, admin gating, user footer menu
    │   ├── dashboard/
    │   │   ├── chart-card.tsx              # icon+title Card wrapper used by every dashboard card
    │   │   ├── dashboard-element-card.tsx  # ChartCard + MetricChart + stats for one configured metric
    │   │   ├── horizontal-bar-list.tsx     # categorical breakdowns (no time axis — not a chart lib)
    │   │   └── monthly-trend-chart.tsx     # lightweight-charts area series for the 12-month trend
    │   ├── metrics/                 # feature components
    │   │   ├── metric-chart.tsx             # lightweight-charts line wrapper — every raw point, never bucketed
    │   │   ├── metric-dashboard.tsx         # timeframe selector + chart + summary stats
    │   │   ├── summary-stat.tsx             # shared current/min/max/avg stat tile
    │   │   ├── threshold-config.tsx         # per-user threshold dialog + useMetricThreshold hook
    │   │   ├── dashboard-element-config.tsx # element picker dialog + useDashboardElementConfig hook
    │   │   ├── metric-entry-dialog.tsx      # create AND edit (pass `entry`) — one form, value-type branching
    │   │   ├── delete-metric-entry-button.tsx     # icon button + AlertDialog confirm, per entry row
    │   │   ├── create-metric-type-dialog.tsx      # incl. the choice-option row editor and is_singleton switch
    │   │   ├── formula-builder/             # canvas/palettes/preview + use-formula-builder.ts state hook
    │   │   └── bulk-import/                 # bulk-import.tsx + use-bulk-import.ts hook + preview-table.tsx
    │   ├── nutrition/                # feature components (Phase 1)
    │   │   ├── food-item-dialog.tsx         # create AND edit (pass `item`) — same pattern as MetricEntryDialog
    │   │   ├── delete-food-item-button.tsx  # icon button + AlertDialog confirm, per row
    │   │   ├── meal-entry-dialog.tsx        # create AND edit (pass `entry`) — Phase 2; itemType toggle (food item/recipe) added Phase 4
    │   │   ├── delete-meal-entry-button.tsx # icon button + AlertDialog confirm, per row — Phase 2
    │   │   ├── recipe-dialog.tsx            # create AND edit (pass `recipe`) — ingredient row editor + live estimate — Phase 4
    │   │   └── delete-recipe-button.tsx     # icon button + AlertDialog confirm, per row — Phase 4
    │   ├── auth-provider.tsx        # current-user context, backed by TanStack Query
    │   ├── query-provider.tsx
    │   ├── theme-provider.tsx
    │   └── theme-toggle.tsx
    └── lib/
        ├── api.ts                   # typed API client — parses every response with Zod
        ├── types.ts                 # Zod schemas + inferred TS types (incl. the FormulaNode AST schema)
        ├── query-keys.ts            # centralized TanStack Query key factories
        ├── metric-bulk-parse.ts     # positional template/line splitting for bulk import (no value parsing)
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

Seed the baseline `NutrientType` catalog (fiber, sugar, saturated fat, cholesterol, sodium, and
common vitamins/minerals — see `apps/nutrition/management/commands/seed_nutrients.py`). Idempotent
(matches on `NutrientType.name`), safe to re-run:

```bash
docker compose exec backend python manage.py seed_nutrients
```

Seed the four materialized daily-total `MetricType`s (Калории/Белки/Жиры/Углеводы (день)) and, if
`seed_metrics` has already run, the "% дневной нормы калорий" formula comparing them against TDEE
— see `apps/nutrition/management/commands/seed_nutrition_metrics.py`. Run `seed_metrics` first (or
re-run this command afterward) to get the TDEE-comparison formula too; idempotent either way:

```bash
docker compose exec backend python manage.py seed_nutrition_metrics
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
| Bulk metric-entry import (`MetricImportSettings` per-user-per-metric-type saved template; `GET`/`PUT /api/metric-types/<id>/import-settings/` + `POST .../import/preview/` + `POST .../import/`, all ownership-scoped actions on `MetricTypeViewSet`; shared `resolve_bulk_import_items`/`execute_bulk_import` in `apps/metrics/services.py` — one parsing/classification path for preview and create; ported, domain-agnostic `TemplateBuilder`/`SeparatorField` components under `components/shared/`; `components/metrics/bulk-import/` page supporting paste + `.csv`/`.txt` upload, template builder with an advanced raw-template mode, per-row new/duplicate-skip/duplicate-overwrite/invalid preview, and a save-as-default action) | `feature/bulk-metric-import` | Implemented, manually verified end-to-end via browser (Weight metric: template built via field toggles, numeric parsing incl. decimal-separator switch, invalid/missing-value rows flagged with reasons, duplicate skip and overwrite both verified against the DB — overwrite updates the existing row in place rather than creating a new one, `.csv` file upload filling the textarea, "set as default" persisting and pre-filling on next visit after a page reload; Activity Level metric: choice-code and choice-label matching both case-insensitive, unknown value flagged invalid); backend: 172/172 tests passing incl. 29 new for bulk import (found and fixed two real bugs via manual testing: a "." wrongly treated as a thousands separator for an already-unambiguous number under `decimal_separator=","`, and DRF's default `trim_whitespace=True` rejecting a legitimate space-only separator), `ruff check .` clean on every file this pass touched; frontend: `eslint`/`tsc` clean |
| Bugfix: `favorites_chart_data_for_user` (`apps/metrics/selectors.py`) hand-built its `metric_type` dict and drifted out of sync with `MetricTypeSerializer`'s fields (missing `is_singleton`/`choices`, added by the choice-metrics/formula-engine and singleton-metric passes respectively) — the frontend's Zod `metricTypeSchema` rejected the response, so `GET /api/metric-types/favorites/` silently failed client-side (React Query swallows the parse error into an error state with no console log). Broke three things off one root cause: the favorite star always showed unselected (`useIsFavoriteMetric` reads the same query), the dashboard's "Избранное" section always showed the empty state despite real favorites existing, and favorited charts never rendered (they live inside that broken section). Fixed by building the dict via `MetricTypeSerializer(metric_type).data` instead of hand-listing fields, so it can't drift again | `feature/bulk-metric-import` | Fixed, manually verified via browser (favorite star now reflects true state and toggles correctly, dashboard favorites section renders both cards with real chart data); backend: 173/173 tests passing incl. 1 new regression test asserting the full `metric_type` key set in the favorites response, `ruff check .` clean on the changed file |
| `MetricEntry` admin-widening removed: `metric_entry_list_for_user` used to widen reads to every user's entries for an admin, and `MetricEntryPermission.has_object_permission` let an admin edit/delete anyone's entry — both were a pre-existing inconsistency with the "MetricEntry is ownership-based, not admin-gated" rule already stated at the bottom of this file, and surfaced as a real, confusing symptom: on a metric's detail page, the entries table (widened for admins) showed rows the chart above it (always scoped to the logged-in user only, per "Timeframe aggregation" above) correctly excluded, reading as "the chart is silently dropping data" with two admin accounts logging the same metric type. Considered adding an Owner column to the table first (smallest change, keeps both scoping rules) but landed on the larger fix instead: `metric_entry_list_for_user` and `MetricEntryPermission.has_object_permission` are now both plain ownership, no admin override, matching `MetricThreshold` exactly — an admin sees/manages only their own entries everywhere, same as everyone else | `feature/bulk-metric-import` | Fixed, manually verified via browser (metric detail page's entries table now shows only the logged-in user's own rows, matching the chart above it); backend: 173/173 tests passing incl. `test_admin_cannot_edit_others_entry`/`test_admin_only_sees_own_entries` replacing the old admin-widening assertions, `ruff check .` clean; frontend: `eslint`/`tsc` clean. **Dev-loop note**: mid-investigation, an unrelated frontend edit didn't show up despite no compile errors in `docker compose logs frontend` — HMR reported "connected" but Turbopack never recompiled the route (confirmed by fetching the served JS chunks directly and finding the new code genuinely absent). A `docker compose restart frontend` fixed it; worth trying first if a change silently doesn't apply |
| Per-card timeframe selector on favorite dashboard charts + 24h/7d/30d/3m/1y period-change badges (`selectors.period_changes_for_metric_type`/`aggregation.period_percent_changes`, new `period_changes` field on both `GET /aggregate/` and `GET /favorites/`; frontend `RangeSelect`/`useMetricAggregate`/`RANGE_PRESETS` extracted so the metric detail page and every favorite card share one range-picker implementation instead of two; `PeriodChangeBadges` shown via `ChartCard`'s new `titleExtra` slot and next to the detail page's `<h1>`; new `--success` CSS token alongside `--destructive` for the green/red coloring) | `fix/metric-entry-ownership-scoping` | Implemented, manually verified via browser (favorites section renders correct % values/colors/`—` placeholders for both a computed metric (BMI, no data old enough → all `—`) and a regular one (Weight, real 24h/7d/30d deltas); the detail page shows the same badges next to the metric name; API responses spot-checked directly). backend: 182/182 tests passing incl. 9 new (`TestPeriodPercentChanges` in `test_aggregation.py`, `period_changes` coverage in `test_aggregate_api.py`/`test_favorites.py`), `ruff check .` clean; frontend: `eslint`/`tsc` clean. Interactive click-through of the range dropdown was confirmed working in a follow-up pass (dispatching a real pointerdown/mousedown/pointerup/mouseup/click sequence via JS gets the Base UI popover to position correctly under this session's CDP-driven browser tool — a plain synthetic click alone left it collapsed to a 0×0 box; not a code issue, just what this popover needs from the automation layer). Hit the Granian dev-loop quirk documented above mid-session — `docker compose restart backend` was needed once for edits to actually take effect |
| Bugfix: `PERIOD_CHANGE_LOOKBACK` (`apps/metrics/selectors.py`) was `relativedelta(years=1)` — exactly equal to the longest entry in `PERIOD_CHANGE_SPECS` ("1y") — so the period-changes points query's `range_start` landed exactly on the "1 year ago" target, leaving no older points to fall back to when nothing was recorded on that exact day. Any entry older than a year (e.g. a first-ever reading logged ~2 years back, with nothing else until recently) fell entirely outside the fetch and was invisible to `value_at_or_before`, so the `1y` (and often `3m`) badge always showed "no data" even though a genuinely comparable old point existed. Fixed by widening `PERIOD_CHANGE_LOOKBACK` to `relativedelta(years=100)` — same "100 years back" stand-in for "unbounded" the frontend's `rangeAll` preset already uses (`relativeDays: 36500`) | `fix/metric-entry-ownership-scoping` | Fixed, manually verified via browser (a Weight entry ~2 years old now correctly resolves the `1y`/`3m` badges instead of showing `—`); backend: 183/183 tests passing incl. 1 new regression test (`test_period_change_finds_data_older_than_the_period_itself`), `ruff check .` clean |
| Dashboard elements (`DashboardElement` per-user/per-metric-type model replaces boolean `FavoriteMetric` entirely, migration `0011` backfills existing favorites as `show_chart=True, timeframe="all"`; per-metric chart/current/max/min/avg toggles + independent timeframe incl. a `custom` date-range option, configured from the metric detail page via `DashboardElementConfigDialog`, not the dashboard itself; `POST`/`PATCH`/`DELETE /api/metric-types/<id>/dashboard-element/` + `GET /api/dashboard-elements/` + `PATCH /api/dashboard-elements/reorder/`; `current` is always the latest entry regardless of timeframe; works uniformly for computed metric types with no special-casing; `GET /aggregate/` gained a `current` field instead of a new overlapping endpoint; new shared `components/metrics/summary-stat.tsx` + `components/dashboard/dashboard-element-card.tsx`) | `feature/dashboard-elements` | Implemented, manually verified end-to-end via browser (configured chart+current+max for Weight, block appeared on the dashboard with only the enabled stats; switched to a custom date range and confirmed the data resolved correctly while current stayed the single latest value; verified current stays correct even when the latest entry falls outside the selected range; BMI computed metric type configured and rendered identically to a regular metric, no special-casing; unconfigured-save validation and the explicit "Убрать с дашборда" removal flow both confirmed against the DB; light/dark theme checked). Found and fixed one real bug via manual testing: a shadcn `Button` rendered as a `Link` (the dashboard block's "reconfigure" action) needs `nativeButton={false}` or Base UI logs a console warning and degrades button semantics. backend: 191/191 tests passing incl. 36 new/updated for dashboard elements and `/aggregate/`'s `current` field, `ruff check .` clean on every file this pass touched (18 pre-existing `E501` errors in untouched test files predate this branch); frontend: `eslint`/`tsc` clean. Hit both documented dev-loop quirks mid-session (stale Granian reload after a mid-edit import error, stale Turbopack HMR) — restarting the respective container fixed each |
| Two small bugfixes: (1) a `number`-valued `MetricEntry`'s value `Input` was `type="number"`, whose accepted decimal separator follows browser/OS locale — under Russian locale that's a comma, so typing `4.4` silently dropped the fractional part; switched to `type="text"` + `inputMode="decimal"`, normalizing `,`→`.` at submit (see "Computed metrics"-adjacent `MetricEntryDialog` notes above). (2) Bulk import's `{date}` token always discarded any parsed time-of-day and hardcoded midnight (`time.min`) as `recorded_at`'s time component; `services._parse_bulk_date` now returns a full `datetime`, using the parsed time when `date_format` contains a time directive (`%H`/`%I`/`%M`/`%S`/`%p`, detected via regex on the format string) and falling back to the current time of day otherwise — date stays required, only time is optional | `feature/dashboard-elements` | Fixed, manually verified via browser (typed `4.4` into the Уровень сахара number field and confirmed it saved and displayed as `4.4`, not `4`; bulk-import preview with a date-only format showed the actual current time instead of `00:00:00`, and a format with `%H:%M` correctly carried the parsed time through to `recorded_at`); backend: 193/193 tests passing incl. 2 new regression tests (`test_date_only_format_uses_current_time_not_midnight`, `test_date_format_with_time_directive_preserves_parsed_time`), `ruff check .` clean on every file this pass touched (18 pre-existing `E501` errors in untouched test files predate this branch); frontend: `eslint`/`tsc` clean. Hit the documented stale-Turbopack-HMR dev-loop quirk once mid-session — `docker compose restart frontend` fixed it |
| Bugfix: charts always show candlesticks-when-spread + OHLC-bucketed values, contrary to product intent — `MetricChart` dropped its `shouldRenderCandlesticks` heuristic/`CandlestickSeries` branch entirely (line-only, no exceptions for any timeframe or data shape), and both `GET /aggregate/` and `dashboard_element_stats` stopped calling `bucketize` for the chart series, returning a flat `points` list (every raw entry in range, chronological) instead of `buckets` — a `1y`/`3y`/`all` chart previously collapsed many entries into one bucket's `close` value per week/month, hiding all the intermediate readings; now every logged value is its own point on the line, at any timeframe. `bucketize`/`OHLCBucket` stay in `aggregation.py` (still covered by their own unit tests) since nothing about the underlying utility was wrong — only the chart-facing call sites were removed. `MetricChart` dedupes points landing on the same whole second (`lightweight-charts` requires strictly increasing unique timestamps), keeping the later value | `feature/dashboard-elements` | Fixed, manually verified end-to-end (seeded 6 same-day blood-sugar entries with real spread — previously enough to trigger candlesticks in a day bucket — and confirmed via a direct API check that `/aggregate/` now returns all 6 as individual `points`, not one bucket; summary min/max/avg on the metric detail page matched the raw entries); backend: 193/193 tests passing incl. `test_aggregate_api.py`/`test_dashboard_elements.py` updated from bucket to point-count assertions, `ruff check .` clean on every file this pass touched; frontend: `eslint`/`tsc` clean. Hit the documented stale-Granian-reload dev-loop quirk mid-session (the aggregate endpoint kept serving the old `buckets` shape after the `views.py`/`selectors.py` edit) — `docker compose restart backend` fixed it |
| Threshold bound lines on charts + time-in-range as a dashboard element (`GET /aggregate/` and `dashboard_element_stats` both gained a `threshold` field — `{lower_bound, upper_bound}` or `null`, resolved from the same `MetricThreshold` fetch each already did for `time_in_range_percent` — and `MetricChart` draws each non-null bound as a red dashed `series.createPriceLine`; new `DashboardElement.show_time_in_range` boolean (migration `0012`), computed via the existing `aggregation.time_in_range_percent` over the same resolved-range points used for max/min/avg, wired into `DashboardElementInputSerializer`'s "at least one `show_*`" validation, `DashboardElementConfigDialog`'s toggle list, and `DashboardElementCard`'s stat row reusing the detail page's existing `statTimeInRange` label) | `feature/dashboard-elements` | Implemented, manually verified end-to-end via browser (seeded a 4.0-6.5 threshold on the blood-sugar metric type with 6 entries spanning in- and out-of-range values; confirmed via direct API checks that both `/aggregate/` and `/api/dashboard-elements/` return the correct `threshold` object and `time_in_range_percent` matching 5/6 in-range = 83.3%; enabled chart + time-in-range on the dashboard-element config dialog, saved, and confirmed the dashboard block renders the time-in-range stat; no console errors from `createPriceLine`); backend: 198/198 tests passing incl. 5 new (`test_time_in_range_only_present_when_show_time_in_range_true`, `test_time_in_range_is_null_without_a_configured_threshold`, `test_chart_includes_threshold_for_bound_lines`, `test_saving_show_time_in_range_only_is_accepted` in `test_dashboard_elements.py`, plus a `threshold`-field assertion in `test_aggregate_api.py`), `ruff check .` clean on every file this pass touched; frontend: `eslint`/`tsc` clean |
| Nutrition module Phase 1 — food item core (new `apps/nutrition` Django app; `NutrientType` catalog, role-gated like `MetricType`, seeded via `seed_nutrients` with the usual vitamins/minerals + sub-macro breakdown nutrients; `FoodItem` — ownership-based, not shared, fixed `calories`/`protein`/`fat`/`carbs` Decimal columns + a `FoodNutrientValue` join table for arbitrary micronutrients, `source`/`external_id`/`is_verified` present on the model but read-only via the API this phase (own/verified only — external-search import is a later phase); `GET/POST/PATCH/DELETE /api/food-items/` incl. `?search=` by name, `GET /api/nutrient-types/`; frontend `FoodItemDialog` create+edit incl. a nutrient-value row editor, `DeleteFoodItemButton`, `/nutrition` list/search page, new sidebar "Питание" group) | `feature/nutrition-food-items` | Implemented, manually verified end-to-end via browser (created "Куриная грудка" with macros + a Vitamin C value, edited its calories, searched by substring match and by a non-matching term, deleted it — each step reflected correctly in the table); backend: 211/211 tests passing incl. 13 new for nutrition (`test_nutrient_types.py`, `test_food_items.py`), `ruff check .` clean on every file this pass touched (pre-existing `E501` errors in untouched metrics test files predate this branch); frontend: `eslint`/`tsc --noEmit` clean. `other_user` fixture promoted from `tests/metrics/conftest.py` to the shared root `tests/conftest.py` now that a second test package needs it. Recipes, meal planning, and the Open Food Facts integration are later phases, not yet built. |
| Nutrition module Phase 2 — meal logging (`MealEntry` — ownership-based, `food_item` required FK (`recipe` not wired up until Phase 4), per-entry `calories`/`protein`/`fat`/`carbs` computed from the food item rather than stored; `GET/POST/PATCH/DELETE /api/meal-entries/` incl. `?date=` filter; daily calorie/macro totals exposed through the *existing* formula-metric engine by materializing them as ordinary `MetricEntry` rows — `services.recompute_daily_nutrition_metrics`, called on every `MealEntry` create/update/delete — onto four new non-computed `MetricType`s seeded by `seed_nutrition_metrics`, so they get charts/timeframes/dashboard elements with zero changes to `apps.metrics`; a further computed `MetricType`+`FormulaDefinition` "% дневной нормы калорий" compares daily calories against the existing TDEE formula using only the engine's existing `/`/`*` nodes; frontend `MealEntryDialog` create+edit incl. a food-item picker and a `defaultDate` seed, `DeleteMealEntryButton`, `/nutrition/log` food-diary page with a date picker, client-side-summed daily-total `SummaryStat` tiles, and an entry table; sidebar gained "Дневник питания" above "Продукты") | `feature/nutrition-meal-logging` | Implemented, manually verified end-to-end via browser (logged a 150g chicken-breast breakfast, confirmed the diary's totals and per-entry calories matched the expected math; edited the quantity to 200g and confirmed both the diary and the materialized `MetricEntry` recomputed; deleted the entry and confirmed both the diary and the materialized entry cleared instead of showing a stale zero; the new "Калории (день)" metric type rendered correctly on its own detail page using the *unmodified* chart/summary UI, and — after configuring a dashboard element for it through the *unmodified* `DashboardElementConfigDialog` — on the dashboard itself; the seeded "% дневной нормы калорий" formula evaluated a real percentage against the account's existing TDEE data); backend: 223/223 tests passing incl. 12 new for meal entries/daily-total materialization, `ruff check .` clean on every file this pass touched; frontend: `eslint`/`tsc --noEmit` clean. Known limitation documented above: the four daily-total metric types aren't `is_computed` (a materialization constraint, not an oversight), so nothing currently stops a manual `MetricEntry` against them — self-heals on the next meal edit for that day, but not actually prevented. |
| Nutrition module Phase 4 — recipes (`Recipe`/`RecipeIngredient` — ownership-based, a recipe is a named "union of products": an owner, `servings` the whole recipe yields, `cost`, and a nested `ingredients` list of `FoodItem`+`quantity_g` rows written atomically via `services.create_recipe_with_ingredients`/`update_recipe_ingredients`; nutrient totals are never stored, only computed at read time by new `selectors.food_item_macro_totals`/`recipe_macro_totals`/`recipe_macro_totals_per_serving`, exposed as 8 flat fields on `RecipeSerializer` with no N+1 thanks to `ingredients__food_item` prefetching; `MealEntry.food_item`/`quantity_g` became nullable, gained nullable `recipe`/`servings`, and a `mealentry_exactly_one_of_food_or_recipe` `CheckConstraint` (migration `0003`) — enforced again in `MealEntrySerializer.validate`; new `selectors.meal_entry_macro_totals` turns either kind of entry into calories/protein/fat/carbs and is now the one function both `MealEntrySerializer` and `services.recompute_daily_nutrition_metrics` call, so the Phase 2 daily-total materialization sums recipe-based entries with zero special-casing; `GET/POST/PATCH/DELETE /api/recipes/` incl. `?search=`, new ownership-scoped `RecipePermission`; frontend `RecipeDialog` create+edit with an ingredient row editor and a live client-computed calorie estimate, `DeleteRecipeButton`, `/nutrition/recipes` list/search page, sidebar gained "Рецепты" below "Продукты"; `MealEntryDialog` gained an itemType (food item/recipe) toggle that swaps the picker and quantity/servings input, and the food-diary table shows a "рецепт" badge + `× servings` for recipe-based rows) | `feature/nutrition-recipes` | Implemented, manually verified end-to-end via browser (created a 2-serving recipe from 200g chicken + 100g rice, confirmed the dialog's live estimate (460 kcal) matched the saved `total_calories` exactly and `calories_per_serving` correctly divided by servings (230); logged a meal against the recipe via the new itemType toggle, confirmed the diary's badge/servings display and per-entry calories (230, i.e. 1 serving eaten); confirmed the materialized "Калории (день)" `MetricEntry` picked up the recipe-based entry's total with no special handling; reopened the entry's edit dialog and confirmed it correctly restored recipe mode with the right recipe pre-selected); backend: 241/241 tests passing incl. 18 new in `test_recipes.py` (recipe CRUD/ownership/search, ingredient-ownership validation, nutrient-total math, recipe-based `MealEntry` creation/servings-scaling/cross-user rejection, exactly-one-of-food-or-recipe validation, daily-total materialization with recipe and mixed food-item+recipe days), `ruff check .` clean on every file this pass touched; frontend: `eslint`/`tsc --noEmit` clean. Branched directly off Phase 2 (not Phase 3, which was still an unmerged sibling branch at the time) — the two Phase-3/Phase-4 slices are independent and don't depend on each other. Hit both documented dev-loop quirks mid-session (a stale Granian reload crash-looping on an `ImportError` for the new `Recipe` model after `makemigrations`/`migrate`, and stale Turbopack routing 404ing the new `/nutrition/recipes` page) — restarting the respective container fixed each. Known limitation documented above: editing a recipe's ingredients doesn't retroactively recompute past days' materialized totals for meals already logged against it — self-heals the next time that day's meals are touched, same accepted staleness class as Phase 2's own daily-total gap. |

`MetricEntry` and `MetricThreshold` are **ownership-based**, not admin-gated: any authenticated
user creates/edits/deletes their own entries and thresholds; only `MetricType` definitions and
`FormulaDefinition`s are admin-only. See "Centralized, extensible permissions" above — this was a
correction partway through the dashboards work, since the original all-admin-gated `MetricEntry`
rule made no sense for a personal tracking app once users other than the admin exist.

No other feature modules (workouts, finances) have been started yet; the nutrition module is under
way (Phases 1-2, 4 above, on separate branches — Phase 3's Open Food Facts integration is also
implemented on its own sibling branch, `feature/nutrition-off-integration`, not yet merged as of
this branch) per the phased plan in its implementation prompt — meal planning and cost-field UI
remain (Phases 5-6).
