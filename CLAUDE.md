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
| App server | [Granian](https://github.com/emmett-framework/granian) (ASGI) — **not** uvicorn/gunicorn |
| Database | PostgreSQL |
| Async / background jobs | Celery + Redis (broker & result backend) |
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind CSS + shadcn/ui |
| Containerization | Docker + Docker Compose (all services run via `docker compose up`) |
| Theming | Light + dark mode out of the box, minimalist design |

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
  `MetricType` and `MetricEntry`. Everyone authenticated can read their own data.

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

### Infrastructure set up ahead of need
Celery + Redis are wired up (broker, result backend, worker service in Compose) starting with the
metrics feature even though no tasks exist yet, so future features (e.g. scheduled aggregation,
reminders) don't require infra work.

## Directory structure

```
life-controller/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── manage.py
│   ├── config/                  # Django project package
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── dev.py
│   │   │   └── prod.py
│   │   ├── urls.py
│   │   ├── celery.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   └── apps/
│       ├── core/                 # shared: PermissionService, base models/mixins
│       ├── users/                 # custom User model (multi-user ready)
│       └── metrics/               # MetricType / MetricEntry — first feature
│           ├── models.py
│           ├── serializers.py
│           ├── views.py
│           ├── permissions.py
│           ├── admin.py
│           ├── urls.py
│           └── tests/
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── app/
    │   ├── layout.tsx             # ThemeProvider (light/dark)
    │   └── metrics/                # MetricType list/create, MetricEntry list/create
    ├── components/
    │   ├── ui/                     # shadcn/ui primitives only
    │   └── theme-toggle.tsx
    └── lib/
        └── api.ts                  # typed API client
```

## Running locally

```bash
cp .env.example .env
docker compose up --build
```

This starts: `db` (Postgres), `redis`, `backend` (Django/DRF served by Granian), `celery-worker`,
and `frontend` (Next.js dev server).

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- Django admin: http://localhost:8000/admin

First-time setup (migrations + an admin user):

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

Backend tests:

```bash
docker compose exec backend python manage.py test
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
| Metrics module (MetricType/MetricEntry backend + admin-only permissions + Docker infra + minimal frontend CRUD UI) | `feature/metrics-module` | In progress |

No other feature modules (nutrition, workouts, finances) have been started yet.
