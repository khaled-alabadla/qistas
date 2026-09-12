# Deploying Qistas to Vercel

Read `docs/adr/0037-vercel-deployment.md` first for *why* this looks the way
it does. This document is the practical checklist.

**Read before you start**: this environment prepared and verified everything
below *locally* (simulated prod settings, a real `collectstatic` run, the S3
storage backend, `manage.py check --deploy`) but could not perform an actual
deploy to Vercel's live infrastructure — there is no Vercel account/CLI
access from here. Treat the first real deploy as the final verification
step, and see "If something doesn't work" at the end.

## 1. Provision what Vercel doesn't provide

Vercel runs the app; it does not give you a persistent disk or a bundled
Postgres for a Python project. You need, before the first deploy:

1. **A PostgreSQL database reachable from the internet.** Vercel Postgres,
   [Neon](https://neon.tech), or [Supabase](https://supabase.com) all work —
   prefer one with a **pooled** connection string (PgBouncer/similar); a
   serverless app can open many concurrent short-lived connections.
2. **An S3-compatible bucket for private documents**, *unless* you're
   comfortable with uploaded documents disappearing (there is no persistent
   disk on Vercel — see ADR-0037). Any of these work:
   - AWS S3
   - [Cloudflare R2](https://developers.cloudflare.com/r2/) — no egress fees,
     a common pairing with Vercel
   - Backblaze B2
   Create the bucket **private** (no public read). Qistas never generates a
   public URL for a document regardless (`PrivateS3Storage.url()` always
   raises) — documents are only ever reachable through the authenticated,
   audited download view — but the bucket itself should not be public either,
   as defense in depth.
3. An SMTP provider for outgoing mail (password resets, notifications), if
   you want real email instead of it failing loudly — same as any other
   production deployment of this app (see `.env.example`).

## 2. Set environment variables in the Vercel project

Project Settings → Environment Variables. At minimum:

```
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<generate: python -c "import secrets;print(secrets.token_urlsafe(64))">
DJANGO_ALLOWED_HOSTS=<your-project>.vercel.app[,your-custom-domain]
DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-project>.vercel.app[,https://your-custom-domain]
DATABASE_URL=postgres://...   # the pooled connection string from step 1
```

For document storage (skip only if you accept documents not persisting):

```
AWS_STORAGE_BUCKET_NAME=qistas-documents-prod
AWS_S3_REGION_NAME=<region, or "auto" for R2>
AWS_S3_ENDPOINT_URL=<only for non-AWS providers, e.g. R2's account endpoint>
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

Set `DJANGO_SETTINGS_MODULE` for **both** the Build and Runtime environment
(Vercel's default scope covers both) — the build step runs `collectstatic`,
which needs `DJANGO_SECRET_KEY`/`DJANGO_ALLOWED_HOSTS`/`DATABASE_URL` to be
importable even though it never queries the database.

Everything else in `.env.example`'s "Production-only" section applies as
normal (email, HSTS, etc.).

## 3. First deploy

```
npm i -g vercel      # or use the Vercel dashboard's Git integration instead
vercel link          # connect this repo to a Vercel project
vercel --prod
```

The build runs (`vercel.json`'s `buildCommand`): install `requirements.txt`,
fetch the Tailwind CLI, build `static/css/app.css`, then `collectstatic`.

## 4. Migrate — manual, not automatic (see ADR-0037)

From a machine that can reach the production database (your laptop, with
the real `DATABASE_URL` pulled from Vercel or set locally):

```
vercel env pull .env.production.local     # or set DATABASE_URL by hand
export $(grep -v '^#' .env.production.local | xargs)   # or just export DATABASE_URL=...
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py migrate
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py sync_roles
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py createsuperuser
```

Re-run `migrate` (and `sync_roles` if groups/capabilities changed) after
every deploy that adds a migration — not on every deploy.

## 5. Verify

- Visit `/accounts/login/` on the deployed URL — should load, not 500.
- Log in, hit `/` (dashboard) — confirms DB connectivity end-to-end.
- Check a page with a table/badge to confirm `/static/css/app.css` and the
  Cairo font files loaded (Network tab, both should be 200, not 404).
- If documents/S3 is configured: upload a small test document, then
  download it back through the app (not by guessing a bucket URL — there
  isn't one).
- `manage.py check --deploy` locally against the real prod env vars, as a
  final sanity check, exactly like CI does (ADR-0026).

## If something doesn't work

**Static files 404 / unstyled page.** The `buildCommand` didn't produce
`staticfiles/`, or it didn't make it into the function bundle. Check the
Vercel build log for the `collectstatic` step's output. If Vercel's Python
builder doesn't carry build-time filesystem changes into the function bundle
the way this ADR assumes (the one thing not verified against live Vercel
infra — see ADR-0037's Consequences), the fallback is: run `python manage.py
collectstatic --noinput` **locally**, commit the resulting `staticfiles/`
directory (remove it from `.gitignore` first), and drop `collectstatic` from
`buildCommand`. Less clean, guaranteed to work.

**500 on every page.** Almost always a missing/wrong env var — check
`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (must include the exact Vercel
domain), `DJANGO_CSRF_TRUSTED_ORIGINS` (needs the `https://` scheme, unlike
`ALLOWED_HOSTS`), and `DATABASE_URL` reachability from Vercel's network
(some DB providers require allow-listing Vercel's egress IPs, or need the
pooled/serverless-specific connection string, not the direct one).

**"relation does not exist" errors.** Migrations haven't been run against
this database yet — see step 4.

**Document upload/download fails with an S3 error.** Double-check
`AWS_S3_ENDPOINT_URL` (only needed for non-AWS providers — leave unset for
real AWS S3), the bucket's region matches `AWS_S3_REGION_NAME`, and the
access key has read+write+delete on that bucket (not e.g. read-only).

**Python version mismatch at build time.** `.python-version` pins `3.13`. If
Vercel's current Python runtime doesn't yet offer 3.13, lower that file to
whatever is offered (`3.12`) and loosen `requires-python` in `pyproject.toml`
to match — nothing in Qistas's own code is 3.13-specific.
