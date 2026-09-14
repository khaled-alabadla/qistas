# قِسطاس — Qistas

Arabic-first, server-rendered case management for a single law office in Palestine — clients, cases, hearings, contracts, documents, and finance in one system, with a full RTL UI, group-based permissions, and an audit trail on every write.

![Login](docs/screenshots/login.png)

## Contents

- [Features](#features)
- [Stack](#stack)
- [Getting started](#getting-started)
- [Everyday commands](#everyday-commands)
- [Tests](#tests)
- [Project layout](#project-layout)
- [Docs](#docs)
- [Contributing](#contributing)

## Features

| Area | What it does |
|---|---|
| **Clients** | Individuals and companies, contact details, status/type filters, search |
| **Cases** | Full case lifecycle, priorities, per-lawyer assignment, linked events |
| **Courts & hearings** | Court directory, hearing scheduling, outcomes |
| **Agenda** | Day/week/month calendar for hearings and deadlines, plus a task list |
| **Documents & contracts** | Per-case/-client document storage, contract tracking |
| **Finance** | Invoices, payments, expenses, case fees — capability-gated, not open to all staff |
| **Reports** | Cross-domain read/export views (no data model of its own) |
| **Notifications** | Per-user in-app inbox for assignments, deadlines, and finance events |
| **Accounts & audit** | Custom email-based user model, groups/capabilities, MFA, login-attempt throttling, and an audit log on every domain write |

**Dashboard** — a single landing page summarizing what needs attention today: overdue invoices, active clients, urgent cases, overdue tasks, today's hearings, and recent activity.

![Dashboard](docs/screenshots/dashboard.png)

**Clients** — searchable, filterable list with status and type at a glance.

![Clients](docs/screenshots/clients.png)

**Agenda** — month/week/day calendar for hearings and deadlines.

![Calendar](docs/screenshots/calendar.png)

## Stack

Django 5.2 LTS · PostgreSQL 16 · Django Templates + Tailwind (utility classes) + HTMX + Alpine.js.
Server-rendered, RTL-first, i18n-ready. No SPA, no DRF, no async worker — background work runs as management commands + cron.

## Getting started

The app **always runs in Docker** so dev matches Linux production ([ADR-0023](docs/adr/)). Your host machine is only the editor.

### Prerequisites
- Docker Desktop (Compose v2)

### First run

```bash
cp .env.example .env            # adjust if needed; DATABASE_URL points at the "db" service
docker compose build
docker compose up
```

Open http://localhost:8000 → redirected to the login page.

Create the first user:

```bash
docker compose exec web python manage.py createsuperuser
```

## Everyday commands

Or use `make <target>` — run `make help` to list all shortcuts.

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations
docker compose run --rm web pytest
docker compose run --rm web ruff check .
docker compose run --rm web python manage.py sync_roles
docker compose run --rm web python manage.py makemessages -l ar --no-location
docker compose run --rm web python manage.py compilemessages
```

### CSS

Tailwind is built from `static/src/app.css` by the standalone CLI (fetched into `bin/` during the image build, not committed). Rebuild with `make css`.

## Tests

```bash
docker compose run --rm web pytest            # full suite, PostgreSQL
DJANGO_TEST_ENGINE=sqlite pytest              # fast local smoke (skips @pytest.mark.postgres)
```

## Project layout

```
config/        settings (base/dev/prod/test), urls, wsgi/asgi, locale formats
core/           abstract models, permission layer, numbering, UI plumbing, error pages
accounts/       custom User, auth flows, groups, django-axes, MFA, session middleware
audit/          AuditLog + event logging + auth-event receivers
clients/        client records (individuals + companies)
cases/          case lifecycle, priorities, assignment
courts/         court directory
hearings/       hearing scheduling and outcomes
agenda/         calendar over hearings/deadlines
tasks/          task/deadline tracking
documents/      per-case/-client document storage
contracts/      contract tracking
finance/        invoices, payments, expenses, case fees
dashboard/      landing-page summary (no models)
reports/        cross-domain read/export views (no models)
notifications/  per-user in-app inbox
templates/      base layout, component kit, error pages, auth templates
static/         Tailwind source, fonts, vendored HTMX/Alpine
docs/           architecture.md + adr/ + phase reports
```

Every domain app follows the same internal shape: writes go through `<app>/services.py`, reads through `<app>/selectors.py`, and object-level access is scoped via `Model.objects.for_user(user)`.

## Docs

- Product spec: [`QISTAS_PROJECT_SPEC.md`](QISTAS_PROJECT_SPEC.md) (source of truth)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Decisions: [`docs/adr/`](docs/adr/) (36+ ADRs)

## Contributing

Work on `phase/N-*` branches → PR into `master` → CI + `/code-review` gate the merge.
`pre-commit install` to run the fast checks locally.
