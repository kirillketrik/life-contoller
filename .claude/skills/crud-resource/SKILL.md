---
name: crud-resource
description: Step-by-step checklist for adding a new CRUD resource to Life Controller (backend model/selector/serializer/permission/viewset/tests, then frontend Zod schema/API client/query keys/dialog/page/i18n). Use whenever a new metrics-layer resource, or anything with the same read/write shape, is being scaffolded.
---

# Adding a CRUD resource

Before reaching for a new Django model, check whether this is actually just a new `MetricType`
row (see CLAUDE.md: "new tracked data is a `MetricType` row, not a new model" — only reach for a
dedicated model when the domain has structure that doesn't fit "one value + optional metadata at
a point in time"). This checklist is for when a genuinely new model is warranted (as
`MetricThreshold` and `FormulaDefinition` were).

Read the `architecture` skill first for the permission-pattern decision (role-gated vs.
ownership) and the selectors convention — this checklist assumes those are already decided.

## Backend

1. **Model** (`apps/<app>/models.py`): add the model with an explicit FK to the owning
   `User`/`MetricType` as appropriate (see "Multi-user ready from day one" in CLAUDE.md — no
   model is single-user). Run `python manage.py makemigrations` inside the backend container.
2. **Selector functions** (`apps/<app>/selectors.py`): a `<resource>_list_for_user(*, user, ...)`
   (or `<resource>_list()` if it's shared/global like `MetricType`) and a
   `<resource>_get(*, ...)`. This is the *only* place querysets get built — mirror
   `metric_threshold_list_for_user`/`metric_threshold_get_for_user` for an ownership-scoped
   resource, or `metric_type_list`/`metric_type_get` for a shared one.
3. **Serializer** (`apps/<app>/serializers.py`): a `ModelSerializer` with the owning-user field as
   `serializers.PrimaryKeyRelatedField(read_only=True)`, and `create()` setting it from
   `self.context["request"].user`. Put cross-field validation in `validate()` (see
   `MetricThresholdSerializer.validate` for the "at least one bound set" / "no duplicate per
   user+type" pattern).
4. **Permission class** (`apps/<app>/permissions.py`): decide role-gated vs. ownership (see the
   `architecture` skill's decision rule), then copy the shape of the matching existing class
   (`MetricTypePermission` for role-gated, `MetricThresholdPermission` for ownership) — don't
   write role logic inline in the permission class; role-gated ones delegate to
   `PermissionService.can()`.
5. **ViewSet** (`apps/<app>/views.py`): a thin `viewsets.ModelViewSet` — `serializer_class`,
   `permission_classes`, `queryset = Model.objects.none()` (required for router basename
   inference), and `get_queryset()` calling the step-2 selector. No business logic in the viewset.
6. **URLs** (`apps/<app>/urls.py`): `router.register("<resource-plural>", XViewSet,
   basename="<resource-singular>")`.
7. **Admin** (`apps/<app>/admin.py`): register it, following the `autocomplete_fields` pattern
   already used for FK-heavy models like `MetricEntry`/`MetricThreshold`.
8. **Tests** (`backend/tests/<app>/test_<resource>.py`): use `authenticated_client`/`admin_client`
   fixtures from the root `conftest.py` and `model_bakery.baker` for fixtures — see
   `backend/tests/metrics/test_thresholds.py` for the shape (requires-auth test, ownership-scoping
   test, validation-error tests). Add resource-specific fixtures to
   `backend/tests/<app>/conftest.py`, not the root one, unless a second test package needs them
   too.
9. Run `docker compose exec backend uv run pytest` and `uv run ruff check .` before moving on.

## Frontend

10. **Zod schema + type** (`lib/types.ts`): a read schema (`xSchema`) and, if creation needs
    stricter validation than the read shape, a separate `createXSchema` — see
    `metricThresholdSchema`/`createMetricThresholdSchema` as the template, including the
    `.refine()` pattern for cross-field validation.
11. **API client functions** (`lib/api.ts`): a small exported object
    (`export const xThings = { list, get, create, update, delete }`) built on the shared
    `request()`/`requestVoid()` helpers — see the `metricThresholds` object for the shape,
    including how `list()`/`create()`/`update()` each pick the right schema.
12. **Query keys** (`lib/query-keys.ts`): a `X_QUERY_KEY` constant (and a `xQueryKey(id)` factory
    if it's parameterized) — plain arrays, no query-key library.
13. **Dialog component** (`components/<domain>/create-x-dialog.tsx` or `x-config.tsx`): follow the
    dialog pattern from the `architecture` skill — local `useState` → Zod `.safeParse` where
    applicable → `useMutation` → invalidate query key(s) + `toast.success` on success,
    `ApiError`-aware `toast.error` on failure. Use the shadcn `Dialog`/`DialogTrigger` primitives,
    never a hand-rolled modal.
14. **Page wiring**: add the list/detail UI under `app/[locale]/...`, gated the same way existing
    pages are (`useAuth()` + redirect-to-`/login` if unauthenticated, `user?.is_admin` check if
    the resource is role-gated).
15. **i18n**: add every new string to `frontend/messages/ru.json` under a new or existing
    namespace matching the component, and use `useTranslations("<namespace>")` — see the
    `ui-design` skill's warning about `MISSING_MESSAGE` errors from a namespace/key mismatch, and
    double-check every key before considering the work done.
16. Run `docker compose exec frontend pnpm exec eslint .` and `pnpm exec tsc --noEmit` (if `tsc`
    reports an error only inside `.next/dev/types/validator.ts`, that's a known Turbopack dev-mode
    artifact bug, not your code — see CLAUDE.md's "Architectural decisions" note. Re-run with the
    frontend dev server stopped, or delete that one file, to get a clean signal).

## Verification

Log in through the actual UI (`docker compose up`, then the browser) and exercise the full
create/read/update/delete flow for the new resource, in both an admin and a non-admin session if
the resource is role-gated or has an admin override — don't rely on passing tests alone to call a
new CRUD resource done.
