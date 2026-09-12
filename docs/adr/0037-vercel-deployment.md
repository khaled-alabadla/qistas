# ADR-0037 — Vercel deployment path

- **Status:** Accepted — 2026-09-12
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0023 (Docker/PostgreSQL parity), ADR-0024 (UI/RTL foundation,
  static asset vendoring), ADR-0026 (CI/VCS), ADR-0030 (private document
  storage), ADR-0025 (PostgreSQL as the target database)

## Context

The owner asked to deploy Qistas on Vercel. Every prior deployment decision
(ADR-0023, the `Dockerfile`/`docker-compose.yml`, `scripts/entrypoint.sh`)
assumed a long-lived container with a writable local disk and a startup
script that waits for Postgres, migrates, and syncs roles before the WSGI
server starts. None of that holds on Vercel:

1. **Vercel's Python runtime is serverless** — each request may hit a fresh,
   short-lived function instance; there is no persistent "container startup"
   step to run `migrate`/`sync_roles` against.
2. **No persistent filesystem.** Qistas's private "documents" storage
   (`documents.storage.PrivateFileSystemStorage`, ADR-0030) writes uploaded
   legal documents to local disk. On Vercel that disk doesn't survive past
   the request (and isn't shared across instances) — every uploaded document
   would silently vanish. This is the one hard blocker; everything else is
   configuration.
3. **No bundled database.** `docker-compose.yml` provides a `db` service;
   Vercel doesn't run Postgres, so a reachable external Postgres is required
   (Vercel Postgres, Neon, Supabase, or self-hosted) — via the same
   `DATABASE_URL` env var Qistas already reads (`django-environ`, ADR-0025).
4. **Static files** still need to work without whitenoise's usual "long-lived
   process with a warm `STATIC_ROOT`" assumption holding in quite the way it
   does under gunicorn/runserver.

## Decision

### Documents: pluggable storage, not a rewrite

`documents/storage.py` already isolated the private store behind Django's
`STORAGES["documents"]` registry entry and a `FileField(storage=
document_storage)` — no view or service ever touches a filesystem path
directly (`documents/views.py`'s download view calls `document.file.open("rb")`,
which is storage-backend-agnostic). This meant swapping the backend needed
**zero changes to any view, service, selector, or model field** — only a new
storage class and an env-driven switch in `config/settings/base.py`:

- `documents.storage.PrivateS3Storage` — new, `django-storages[s3]`-backed,
  same "`.url()` always raises, only the audited download view can reach a
  document's bytes" contract as `PrivateFileSystemStorage`.
- `STORAGES["documents"]["BACKEND"]` picks `PrivateS3Storage` when
  `AWS_STORAGE_BUCKET_NAME` is set, `PrivateFileSystemStorage` otherwise.
  Docker/local deployments are unaffected (that env var stays unset there).
- Works with any S3-compatible provider (AWS S3, Cloudflare R2, Backblaze
  B2, ...) via the standard `AWS_S3_ENDPOINT_URL` override — no lock-in to
  one vendor, and no dependency on Vercel's own (non-S3-API) Blob product.

### Database

No code change — `DATABASE_URL` already flows through `django-environ`
(ADR-0025). The owner provisions an external Postgres reachable from Vercel's
network (Vercel Postgres / Neon / Supabase are the common serverless-friendly
choices — a connection pooler on the provider side matters more here than on
a long-lived container, since serverless can open many concurrent short
connections). `CONN_HEALTH_CHECKS` was turned on (`DATABASES["default"]`,
`config/settings/base.py`) so a pooled connection a frozen function held past
the DB's own timeout doesn't surface as a request-time error.

### Static files: whitenoise stays, no separate CDN routing

`whitenoise.middleware.WhiteNoiseMiddleware` + `CompressedManifestStaticFilesStorage`
were already in place (ADR-0024) and need no runtime filesystem *writes* —
only `collectstatic` at build time, which is a **read-only** requirement at
request time. `vercel.json`'s `buildCommand` runs the same CSS build the
Dockerfile does (`scripts/fetch-tailwind.sh` + the standalone Tailwind CLI)
and then `collectstatic --noinput`, so `staticfiles/` is fully populated
before the function is packaged. This avoids needing a second `@vercel/static`
build target and route just to serve `/static/*`.

### Migrations and `sync_roles` run out-of-band

There is no per-deploy hook equivalent to `scripts/entrypoint.sh`'s
wait-then-migrate loop. Migrations and `sync_roles` are run **manually**,
from a machine with the production `DATABASE_URL`, before/after a
migration-bearing deploy — not automatically on every build. Auto-migrating
on every Vercel build (including preview deployments for open PRs) risks
concurrent/partial migrations against the same database; a manual step,
gated by the person doing the release, is the safer default for a system
handling legal records. See `docs/DEPLOY_VERCEL.md` for the exact commands.

### One new file family, one new dependency

- `api/index.py` — a thin WSGI adapter Vercel's Python runtime detects (a
  module-level `app` callable). Delegates immediately to the existing
  `config/wsgi.py`; no parallel app-wiring logic.
- `vercel.json` — build command + routing (everything to `api/index.py`).
- `requirements.txt` — generated from `pyproject.toml`'s `[project.dependencies]`
  by `scripts/gen_requirements.py` (Vercel's Python builder reads
  `requirements.txt`, not `pyproject.toml`). Regenerate after any dependency
  change; the file itself says not to hand-edit it.
- `.python-version` — Vercel's Python-version detection. Tracked in git
  despite living in the "virtual environments" section of `.gitignore`
  historically — that ignore rule was for personal pyenv files, not this.
- `django-storages[s3]==1.14.4` — new runtime dependency, used only when
  `AWS_STORAGE_BUCKET_NAME` is set.

## Consequences

- Docker/local deployment is untouched: no env var defaults changed, no
  existing behavior altered when the new Vercel-only env vars are absent.
- Qistas can now run on any platform that can execute a WSGI callable and
  reach an external Postgres + (optionally) S3-compatible bucket — Vercel
  specifically, but the same config also covers Render/Railway/Fly.io if a
  future phase wants to compare hosts.
- **Real limitation, disclosed rather than worked around**: this ADR and the
  accompanying config were prepared and verified locally (WSGI app loads
  under simulated prod settings, `collectstatic` runs clean, the S3 storage
  backend wires up and its `.url()` still raises, `manage.py check --deploy`
  is clean both with and without the S3 env vars set) — but an actual
  deployment to Vercel's live infrastructure was **not** performed from this
  environment (no Vercel account/CLI access here). The exact mechanics of
  Vercel's `buildCommand` step for a Python project — whether it runs before
  `@vercel/python`'s own packaging in exactly the way assumed here — should
  be confirmed against Vercel's current documentation during the first real
  deploy, per `docs/DEPLOY_VERCEL.md`'s troubleshooting section.
- Running Django on a serverless platform trades the Dockerfile's "warm,
  long-lived process" assumptions for "many short-lived, possibly cold"
  ones. Nothing in Qistas's own code relied on in-process state surviving
  between requests (sessions and django-axes are already DB-backed, not
  cache-backed — verified, not assumed, by grepping for `CACHES`/
  `AXES_HANDLER` overrides and finding none), so this ADR did not need to
  change any of that.
