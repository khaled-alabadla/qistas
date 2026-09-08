# قِسطاس — Qistas

Arabic-first Law Practice Management System for a single law office in Palestine.

> **Status:** Phase 1 — Foundation. No domain features yet. See `docs/PHASE_1_PLAN.md`.

- Product spec: [`QISTAS_PROJECT_SPEC.md`](QISTAS_PROJECT_SPEC.md) (source of truth)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Decisions: [`docs/adr/`](docs/adr/)

## Stack

Django 5.2 LTS · PostgreSQL 16 · Django Templates + Tailwind (logical utilities) + HTMX + Alpine ·
server-rendered, RTL, i18n-ready. No SPA, no DRF, no async worker (management commands + cron).

## Development (Docker only — do not run natively)

The app **always runs in Docker** so dev matches Linux production (`docs/adr/0023`).
Your host machine is only the editor.

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

### Everyday commands (or use `make <target>`)
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations
docker compose run --rm web pytest
docker compose run --rm web ruff check .
docker compose run --rm web python manage.py sync_roles
docker compose run --rm web python manage.py makemessages -l ar --no-location
docker compose run --rm web python manage.py compilemessages
```

`make help` lists all shortcuts.

### CSS
Tailwind is built from `static/src/app.css` by the standalone CLI (fetched into `bin/`
during the image build, not committed). Rebuild with `make css`.

## Tests

```bash
docker compose run --rm web pytest            # full suite, PostgreSQL
DJANGO_TEST_ENGINE=sqlite pytest              # fast local smoke (skips @pytest.mark.postgres)
```

## Layout

```
config/        settings (base/dev/prod/test), urls, wsgi/asgi, locale formats
core/          abstract models, permission layer, numbering, UI plumbing, error pages
accounts/      custom User, auth flows, groups, django-axes, MFA, session middleware
audit/         AuditLog + event logging + auth-event receivers
templates/     base layout, component kit, error pages, auth templates
static/        Tailwind source, fonts, vendored HTMX/Alpine
docs/          architecture.md + adr/ + PHASE_1_PLAN.md
```

## Contributing

Work on `phase/N-*` branches → PR into `main` → CI + `/code-review` gate the merge.
`pre-commit install` to run the fast checks locally.
