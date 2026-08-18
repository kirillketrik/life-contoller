---
name: dashboard-chart-card
description: How to add a new KPI stat or chart card to the Life Controller dashboard — picking the right visualization (Lightweight Charts vs. horizontal bars vs. a plain number), wiring backend data, and keeping cards visually consistent. Use whenever the dashboard needs a new card.
---

# Adding a dashboard card

The dashboard (`app/[locale]/page.tsx`) is a KPI row followed by a grid of chart cards, all
sourced from the single `GET /api/dashboard-summary/` endpoint — see the `architecture` skill's
"aggregate once, derive many stats" principle. Extend that one endpoint rather than adding a
second dashboard-data request, unless the new card genuinely needs a different scope/permission
than the rest of the dashboard.

## 1. Decide what kind of card it is

- **A single number** (e.g. "Всего записей"): a `KpiCard` in the KPI row — `icon`, `label`,
  `value`, `loading` props, see `app/[locale]/page.tsx`'s `KpiCard` helper. No new component
  needed, just a new `<KpiCard .../>` call.
- **A time series** (has a real timeline on the x-axis — activity over months/days/hours): use
  **Lightweight Charts**. Follow `components/dashboard/monthly-trend-chart.tsx` (Area series) or
  `components/metrics/metric-chart.tsx` (Candlestick/Line) as the template — same
  `CHART_COLORS`/`ColorType.Solid` theming pattern, same `useTheme()`-driven light/dark handling,
  same cleanup (`return () => chart.remove()`).
- **A categorical breakdown** (label → count/value, no time axis — "records by X"): use
  `components/dashboard/horizontal-bar-list.tsx`, not a charting library. See the `architecture`
  skill's "chart library split" note for why: Lightweight Charts is a time-scale library and a
  categorical breakdown has no time axis to plot against.
- Anything that doesn't fit either — stop and think before reaching for a new charting dependency.
  A brand-new visualization type is rare enough that it's worth a deliberate decision (and a note
  in CLAUDE.md's "Architectural decisions"), not a default.

## 2. Wire the data

- If the number/series can be derived from data `dashboard_summary_for_user` already returns,
  just use it — check `apps/metrics/selectors.py`'s `dashboard_summary_for_user` and
  `frontend/lib/types.ts`'s `dashboardSummarySchema` first.
- If not, extend the selector (add a new key to the dict it returns), extend
  `dashboardSummarySchema` in `lib/types.ts` to match, and add a backend test in
  `backend/tests/metrics/test_dashboard_summary.py` covering the new field (scoping-to-user case
  at minimum, same as the existing tests). Keep it inside the one endpoint — don't add a second
  `GET` for a single new dashboard number unless it has a genuinely different permission scope.

## 3. Build the card

- Wrap it in `components/dashboard/chart-card.tsx`'s `ChartCard` (`title`, `icon`, `children`) —
  every chart card on the dashboard uses this wrapper so they look identical. Don't build a
  one-off `Card`/`CardHeader`/`CardTitle` combination.
- Show a `Skeleton` while `isLoading`, and pass through an empty-state string (translated, via
  `t("noData")` or a new key) for when the series/list is empty — see how both existing chart
  cards in `app/[locale]/page.tsx` do this.
- Add the card's title and any labels to `frontend/messages/ru.json` under the `dashboard`
  namespace (or the relevant component's own namespace if it's a shared component like
  `horizontal-bar-list.tsx` — that one takes its labels as props rather than translating
  internally, so the caller supplies already-translated strings).

## 4. Place it

- KPI cards go in the `grid gap-3 sm:grid-cols-N` row at the top; bump `N` if you're adding a 4th.
- Chart cards go in the `grid gap-3 lg:grid-cols-2` grid below; if you're going past 2 cards,
  confirm the grid still reads well responsively (`lg:grid-cols-2` → consider `xl:grid-cols-3`
  rather than cramming a 3rd column into `lg`).

## 5. Verify

Check the card renders correctly with real data (log in, create some entries), with no data
(empty state), in both light and dark theme, and at a mobile viewport width
(`resize_window` preset `"mobile"` if using the Browser tool) since the dashboard grid reflows to
a single column there.
