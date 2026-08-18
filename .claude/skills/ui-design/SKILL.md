---
name: ui-design
description: Professional, consistent UI/UX patterns for Life Controller — sidebar/nav structure, dashboard card layout, typography, spacing, and Russian-first copy. Use before any UI work (new pages, components, or redesigns) so new screens stay visually consistent with the rest of the app.
---

# Life Controller UI design

This app follows the redesign established on `feature/ui-redesign-i18n`: a fixed left sidebar
(shadcn `Sidebar` primitive), card-based dashboards, Geist Variable typography, and Russian-first
copy via `next-intl`. Follow these patterns for any new UI work instead of inventing new ones.

## Layout shell

- The root shell lives in `app/[locale]/layout.tsx`: `SidebarProvider > AppSidebar +
  SidebarInset(header bar with SidebarTrigger + ThemeToggle, then <main>)`. New top-level pages
  are just a `page.tsx` under `app/[locale]/...` — they automatically get the sidebar shell, no
  per-page layout work needed.
- Never hand-roll a sidebar, dropdown, dialog, tooltip, sheet, or collapsible — use the shadcn
  primitives already installed in `components/ui/`. If a primitive you need isn't there yet,
  install it with `pnpm dlx shadcn add <name>` **through the frontend Docker container**
  (`docker compose exec frontend pnpm dlx shadcn add ...` — Node/pnpm aren't on the host `PATH`,
  and the container's `node_modules` is a separate named volume from any host install).

## Sidebar (`components/layout/app-sidebar.tsx`)

- Structure: brand header (icon + wordmark, links to `/`) → flat top-level links (e.g. Дашборд)
  → `Collapsible` + `SidebarGroup` sections for related items (e.g. "Метрики") → an admin-only
  `Collapsible` group (gated on `user.is_admin`, same as the old navbar's gate) → footer
  `DropdownMenu` with the user's avatar/name/admin badge and Редактировать/Выйти actions.
- Active-state highlighting: `SidebarMenuButton isActive={pathname === "/x"}` (or
  `pathname.startsWith("/x")` for a section with sub-routes) using `usePathname` from
  `@/i18n/navigation` (not `next/navigation` — see the architecture skill's i18n section for why).
- Every internal link goes through `Link`/`usePathname`/`useRouter` imported from
  `@/i18n/navigation`, never `next/link`/`next/navigation` directly — that wrapper is what keeps
  links locale-aware if a second locale is ever added.

## Dashboard card pattern

- KPI row: a `grid gap-3 sm:grid-cols-N` of plain `Card`s, each with a `CardHeader` (label +
  small `lucide-react` icon, muted) and a `CardContent` with a large `text-2xl font-semibold
  tabular-nums` number. See the `KpiCard` helper in `app/[locale]/page.tsx`.
- Chart/content cards: wrap in `components/dashboard/chart-card.tsx`'s `ChartCard` (icon + title
  header, content below) so every chart card looks identical — don't build a one-off `Card` +
  header combination for a new chart.
- Choosing the right visualization for a chart card is an architecture question — see
  `dashboard-chart-card` skill before adding one.
- Always render a `Skeleton` while loading and an explicit "no data" string (translated) when a
  series/list is empty — every existing card does this; don't ship a card that silently renders
  nothing.

## Typography & tokens

- Global font is **Geist Variable** via `@fontsource-variable/geist`, imported once in
  `app/[locale]/layout.tsx`. Don't add another font or reach for `next/font/google` — that was
  explicitly replaced (see CLAUDE.md's "Architectural decisions").
- Never hardcode a color. All color/spacing/radius values are CSS variables defined in
  `app/globals.css` (`--background`, `--sidebar-*`, `--chart-1..5`, `--radius*`, etc.) and consumed
  through Tailwind utility classes (`bg-background`, `text-muted-foreground`, `rounded-xl`, ...).
  This is what makes light/dark mode (and the sidebar's own token set) work without per-component
  theme logic.
- Spacing: stick to the Tailwind scale already in use (`gap-3`, `gap-4`, `space-y-6`, card
  padding via the `Card` primitive's own `--card-spacing`) rather than introducing arbitrary
  pixel values.

## Copy: Russian first

- Default UI language is Russian. Every new user-facing string — including accessibility-only
  text like `aria-label`s, `sr-only` spans, and dialog descriptions — goes through `next-intl`:
  `useTranslations("namespace")` in client components, `getTranslations("namespace")` in server
  components. Never hardcode an English (or Russian) string directly in JSX.
- Add new copy to `frontend/messages/ru.json` under a namespace matching the component/page (see
  the existing namespaces: `nav`, `dashboard`, `metrics`, `metricDetail`, `metricEntry`,
  `threshold`, `metricDashboard`, `metricChart`, `formulas`, `sidebar`, `common`, `login`). Reuse
  `common` for generic strings (Сохранить/Отмена/Закрыть/...) instead of duplicating them
  per-namespace.
- **Before shipping, verify every `t("key")` call actually resolves** — a namespace/key typo
  doesn't fail to build, it throws `MISSING_MESSAGE` at render time (this has bitten this exact
  redesign once: a dialog referenced `metrics.create` when only `common.create` existed). Grep
  the component's `t("...")` calls against its namespace block in `messages/ru.json` before
  calling the work done, especially for dynamic lookups like `t(someMap[key])`.
- The architecture is deliberately ready for a second locale (e.g. `en`) later — see
  `frontend/i18n/routing.ts`. Adding one is: append to `locales`, add `messages/en.json`. Don't
  build anything that assumes Russian is the only locale that will ever exist.

## Client vs. server components

- Default to server components. A component only needs `"use client"` if it uses a hook
  (`useState`, `useQuery`, `usePathname`, ...), an event handler, or a browser API.
- `components/dashboard/chart-card.tsx` and `horizontal-bar-list.tsx` are plain server components
  (no hooks) — that's the target for any new purely-presentational wrapper. Dialogs, the sidebar,
  and anything with TanStack Query stay client components — that's fine, don't force them server-side.
