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
- Adding a new role (e.g. "editor" who can create `MetricEntry` but not `MetricType`) means
  changing `PermissionService` only — no view rewrites.
- Today: only admins (members of the `admin` Django group, or superusers) can create/update/delete
  `MetricType` and `MetricEntry`. Everyone authenticated can read their own data (admins can read
  everyone's).
- The frontend also gates admin-only actions in the UI (via `GET /api/auth/me/`'s `is_admin`
  flag), but that's a UX nicety only — the backend permission is the actual boundary.

### Generalized metrics layer
This is the foundational abstraction for the whole app — **not** hardcoded to specific metric
types (weight, blood sugar, insulin dose, water intake, etc. are all just data).

- **`MetricType`** (admin-defined): `name`, `unit`, `value_type` (`number` / `text` / `boolean`),
  optional `aggregation` hint (`sum` / `last` / `avg`, for future dashboards), `created_by`.
- **`MetricEntry`**: FK to `MetricType`, FK to the owning `User`, `value` (`JSONField` — shape
  depends on `value_type`), optional `context` (`JSONField` — free-form metadata such as
  `{"reason": "post-meal", "injection_site": "abdomen"}`), `recorded_at` timestamp.
- New kinds of tracked data should almost always be a new `MetricType` row, not a new Django
  model/migration. Only reach for a dedicated model when the domain has structure that doesn't
  fit "one value + optional metadata at a point in time" (e.g. multi-line finance transactions
  later on).

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
│   │   └── metrics/               # MetricType / MetricEntry — first feature
│   │       ├── models.py
│   │       ├── selectors.py       # all read-query logic for this app
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
    │   └── metrics/
    │       ├── page.tsx             # MetricType list + create (admin-gated)
    │       └── [id]/page.tsx        # MetricEntry list + create for one MetricType
    ├── components/
    │   ├── ui/                      # shadcn/ui primitives only
    │   ├── metrics/                 # feature components (create dialogs)
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
| Metrics module (MetricType/MetricEntry backend + centralized admin-only permissions + session auth + Docker infra incl. MinIO + frontend CRUD UI with TanStack Query/Zod) | `feature/metrics-module` | Implemented, manually verified end-to-end via browser (login, create metric type, log entry, admin vs. non-admin gating, light/dark theme) |

No other feature modules (nutrition, workouts, finances) have been started yet.
