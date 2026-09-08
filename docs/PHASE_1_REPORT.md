━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:
1 — Foundation

Status:
COMPLETE (technical) — **PostgreSQL / Docker verification DEFERRED** (the session
environment could not run either; see Known Issues). All other DoD items met.

Branch:
`phase/1-foundation` — **one commit** `phase(1): complete foundation`, **pushed** to
`origin`. **Not merged** to `main`/`master`.

---

Implemented:
- **Project scaffold** — `pyproject.toml` (pinned deps), split settings (`base/dev/prod/test`), `config/` package, `manage.py`, wsgi/asgi, `config/formats/ar` (Western digits pinned).
- **Docker dev** — `Dockerfile` + `docker-compose.yml` (`web` + `db:postgres16` + `media` volume), `scripts/fetch-tailwind.sh`, `scripts/entrypoint.sh`, `Makefile`, `README.md`. App runs in Docker for Linux parity (ADR-0023).
- **CI** — `.github/workflows/ci.yml`: PG16 service, `ruff` + `ruff format --check`, `pytest` + coverage, `makemigrations --check`, `check --deploy`, `pip-audit`, `gitleaks`; `.pre-commit-config.yaml` mirrors it. `.gitattributes` (LF).
- **`core` app**
  - abstract models: `TimeStampedModel`, `AuthoredModel`, `SoftDeleteModel` (applied to nothing yet — ADR-0022)
  - object-level authz framework (ADR-0019): `ScopedQuerySet`/`ScopedManager` + `for_user()` contract + `assert_scoped` DEBUG guard + `ScopedListMixin`/`ScopedDetailMixin` (deny → **403**)
  - capability layer (ADR-0007): 5 groups → named capabilities, `can()`, `CapabilityRequiredMixin`, `require_capability`
  - `NumberSequence` + transaction-safe `next_number()` (no consumers — ADR-0021)
  - async seam `core/tasks.py` (empty — ADR-0005); `core/sensitive.py` (`SENSITIVE_FIELDS` + redaction + logging filter — ADR-0009)
  - data-driven permission-aware navigation; `{% can %}` / `{% num %}` (bidi-safe) template tags
  - authenticated landing (Arabic empty-state placeholder), office-manager `/settings/`, dev-only `/styleguide`, `/healthz`
  - themed **400 / 403 / 404 / 500** handlers (standalone, no context processors on 500)
- **`accounts` app**
  - custom `User(AbstractUser)` — `USERNAME_FIELD="email"`, no `username`, `employee_code` extension point, `must_change_password`; email normalised on save (ADR-0004)
  - migration seeds the 5 role `Group` rows; **`sync_roles`** command owns group→permission mapping with `--check` drift mode (CI + test)
  - themed Arabic auth flows: login, logout, password change, password reset chain; admin **"issue temporary password"** action (audited, password never logged) (ADR-0027)
  - **`django-axes`** — lockout **by username only, never IP** (grill D2); `AXES_USERNAME_CALLABLE` resolves the attempted email; `LoginView.dispatch` guard → themed 429 page
  - **MFA** (`django-otp` TOTP) — enrollment (QR + secret + recovery codes), manage/disable, post-login OTP step. **Enrollment not forced** (setting-gated OFF); **completion mandatory once enrolled** (ADR-0017 refinement).
  - middleware: `LoginRequired` (process_view — 404-safe for unknown URLs), `MustChangePassword`, `IdleTimeout` (sliding), `MFAEnforcement`
- **`audit` app**
  - `AuditLog` per spec §46 — **append-only**: instance + bulk `delete()`/`update()` raise `PermissionError`; no admin add/change/delete; `actor` `SET_NULL`; indexed (DB trigger deferred to Phase 12 — ADR-0020)
  - `log_event()` — single entry point; redacts sensitive keys; `ip_address` from `REMOTE_ADDR` (XFF gated on `AUDIT_TRUST_XFF`, validated)
  - auth-event receivers: login / logout / login-failed / user-created / groups-changed (handles `post_clear` + reverse m2m)
  - `django-auditlog` installed + `AuditlogMiddleware` wired; model registration begins Phase 2
- **UI foundation** — `base.html` (`<html lang=ar dir=rtl>`, right sidebar, topbar, toast region, vendored HTMX + Alpine, global `hx-headers` CSRF), `auth_base.html`; Tailwind (logical utilities, **no RTL plugin** — ADR-0024) + `@font-face` IBM Plex Sans Arabic + `.btn` component layer; §49 component kit (18 partials); `/styleguide`.
- **i18n scaffolding** — `USE_I18N`, `LocaleMiddleware`, `locale/` dir, all Phase 1 strings via `gettext`, `LANGUAGE_CODE="ar"`, `FORMAT_MODULE_PATH` → Western digits.
- **Tracking** — `PROJECT_STATUS.md` (14 phases), `docs/PHASE_1_PLAN.md`, `.wolf/STATUS.md` refreshed, ADRs updated.

---

Files Changed:
- One commit `phase(1): complete foundation` on `phase/1-foundation` (~160 files):
  scaffold + Docker + CI · `core` · `accounts` · `audit` · UI · tests · the spec /
  Phase 0 analysis / 27 ADRs / architecture doc. Built and reviewed as a 10-commit
  series during the session (see git reflog), squashed to one at the owner's request.

Database Changes:
- `accounts.User` (custom `AUTH_USER_MODEL`, set before the first migration)
- `accounts` migration 0002 — seed 5 role groups (reversible)
- `audit.AuditLog` (+ indexes on `created_at`, `(entity_type, entity_id)`, `actor`, `action`)
- `core.NumberSequence` (+ unique `(scope, period)`)
- `core` migration 0002 — `pg_trgm` + `unaccent` extensions (vendor-guarded)
- `django-axes`, `django-otp` (totp + static), `django-auditlog` table migrations
- No domain-business tables.

---

Tests:
Total:   102 collected
Passed:  100
Failed:  0
Skipped: 2  — both `@pytest.mark.postgres` (`pg_trgm`/`unaccent` present after migrate;
             `NumberSequence` concurrency with real row locking). They run **only** on a
             PostgreSQL backend and are therefore **UNVERIFIED** this session.

Also run: `ruff check` ✓ · `ruff format --check` ✓ · `pip-audit` ✓ (pytest bumped 8.4.2→9.0.3
for PYSEC-2026-1845) · `makemigrations --check` ✓ · `manage.py check --deploy` ✓ on prod settings.

Coverage of Tier-1 areas (ADR-0025): authentication · authorization (capability + object-level
+ URL-tampering) · reference-number allocation · audit-write + append-only · lockout
(username-only, cross-account isolation, admin unlock) · MFA enrollment + completion enforcement
+ gate · sensitive-data log scrubbing · `sync_roles` drift · themed errors · i18n / Western
digits · smoke.

**Run on SQLite** (`DJANGO_TEST_ENGINE=sqlite`) — the canonical PostgreSQL 16 run is
**DEFERRED**, see Known Issues.

---

Code Review:
PASS (all findings fixed before this commit)
- `/code-review` (high effort) returned **8 findings**, all addressed:
  1. MFA redirect loop (`mfa_setup`→`mfa_manage` not allow-listed) — fixed
  2. Audit IP forgery via client `X-Forwarded-For` — now `REMOTE_ADDR` unless `AUDIT_TRUST_XFF`, IP-validated
  3. `groups_changed` signal wrong on `post_clear` / reverse-m2m — fixed
  4. `SensitiveDataFilter` no-op on positional log args — now scrubs the rendered message
  5. prod `SECRET_KEY` fell back to the dev default — now required
  6. MFA skippable once enrolled — completion now enforced by middleware
  7. `ScopedDetailMixin` hardcoded `slug`/`pk` kwarg names — now honours `*_url_kwarg`
  8. `login_failed` crash on `username=None` — coerced to str
- Regression test added for each (2, 3, 4, 6, 7, 8; 1 & 5 covered by existing MFA/deploy tests).

Security Review:
PASS (auth-focused, self-review — spec §70)
- Session fixation (Django cycles key on login), CSRF (middleware + `{% csrf_token %}` + HTMX `hx-headers`, `CSRF_COOKIE_HTTPONLY=True`), user-enumeration-safe password reset, open-redirect-safe `next` (`redirect_to_login`), timing-safe login (Django), brute-force (axes, username), MFA completion enforced once enrolled, temp password not logged, prod `SECRET_KEY` required (no fallback), `check --deploy` clean, append-only audit trail, security headers + HSTS in prod.
- Noted for later: OTP-attempt rate limiting → Phase 12; recovery codes stored plaintext (django-otp default) → Phase 12; audit DB-immutability trigger → Phase 12 (ADR-0020).

Performance Review:
PASS (nothing performance-sensitive in Phase 1)
- No domain queries, no dashboard. `capabilities_for` does one `user.groups` query per request via the context processor — acceptable; will add `prefetch`/cache when the nav grows.

---

Known Issues — DEFERRED / UNVERIFIED (owner approved committing with these open):
The session environment could not run PostgreSQL **or** Docker — ~0.28 GB free RAM
(commit charge 87%), Docker Desktop OOM-killed, and the network stalled on every
large pull (`postgres:16`, 338 MB EDB binaries, 15 MB embedded-postgres jar all
timed out). Verified alternatives were used where possible (SQLite suite + `runserver`
end-to-end + static analysis).

1. **Full test suite not run against PostgreSQL 16** — only SQLite. Residual risk is
   low (no domain models; PG-specific schema features barely used in Phase 1) but real.
2. **`core/migrations/0002_postgres_extensions` not executed** — it is vendor-guarded
   (`CREATE EXTENSION pg_trgm, unaccent` runs only on `postgresql`), so SQLite skipped it.
3. **The 2 `@pytest.mark.postgres` tests are unverified** (extensions present; `NumberSequence`
   concurrency with real `SELECT … FOR UPDATE`).
4. **`docker compose build` + `docker compose up`** (full-stack smoke) — not run. The
   equivalent flow *was* verified via `runserver` on SQLite (login → landing → logout,
   role-gated `/settings/`, MFA QR, themed 404, `/healthz`).
5. **`make compilemessages`** — needs GNU gettext (Docker-only on Windows). Harmless:
   ships `ar`, source strings are already Arabic; matters when English is added.
6. Compiled `static/css/app.css` is gitignored — produced by the Docker build / `make css`
   (the Windows Tailwind CLI build was verified locally: 22 KB output).

**Exact remaining PostgreSQL checks** (owner or CI must run before Phase 1 is fully closed):
```
docker compose build
docker compose run --rm web python manage.py migrate       # 0002 extensions apply cleanly
docker compose run --rm web pytest                         # expect 102 passed, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/           # expect 302 -> /accounts/login/
```
CI (`.github/workflows/ci.yml`) already runs the suite against a PostgreSQL 16 service
container, so the first push that opens a PR will execute checks 2–4 automatically.

---

Deferred Items (carried forward, tracked in docs/architecture.md §17):
- All domain models (Client/Case/Court/Hearing/Task/Document/Contract/Invoice/Payment/…)
- Real dashboard, DRF, reports, global search backend, PDF/CSV, notifications, demo data
- `CaseConfidential` side model (Phase 3), office-wide Party directory (Phase 3)
- Audit DB-immutability trigger + partitioning (Phase 12)
- MFA org-wide enforcement rollout decision (Phase 12), OTP rate limiting (Phase 12)
- Production email provider + cron + disk-encryption verification (Phase 14)
- django-auditlog model registration (starts Phase 2)

Technical Debt:
- `SoftDeleteQuerySet.delete()` returns an int, not Django's `(count, {})` — fine (no consumers yet); revisit when the first model adopts soft-delete.
- `sync_roles` warns (doesn't fail) when a mapped permission's app isn't migrated yet — acceptable; `--check` fails hard.
- Recovery codes stored plaintext (django-otp default).

Assumptions:
- One office per deployment; all users are staff (no client login) — ADR-0001, ADR-0015.
- Jurisdiction = Palestine; no jurisdiction logic built yet — ADR-0002.
- PostgreSQL 16 in production with `pg_trgm`/`unaccent` creatable (or pre-created) — ADR-0023.
- Deploy provides `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, a real SMTP config (Phase 14), and disk/DB encryption at rest — ADR-0009.

DoD status (docs/PHASE_1_PLAN.md §6):
| # | Item | Status |
|---|---|---|
| 1 | Migrations apply on empty PostgreSQL 16 | **DEFERRED** — verified on SQLite only |
| 2 | Tier-1 tests pass in CI | met locally (SQLite); CI (PG) runs on first push |
| 3 | `check --deploy` clean on prod settings | ✓ |
| 4 | `docker compose up` full-stack login→landing→logout | **DEFERRED** — equivalent verified via `runserver` |
| 5 | MFA enrollable; enforcement gate-able | ✓ |
| 6 | Lockout by username; admin unlock | ✓ |
| 7 | Nav filters by capability; layer centralized + unit-tested | ✓ |
| 8 | Object-scoping 403 + DEBUG guard | ✓ |
| 9 | Themed 400/403/404/500 with DEBUG=False | ✓ |
| 10 | RTL + bidi verified | ✓ structural (login/landing/styleguide render RTL Arabic; `{% num %}` bidi tested) |
| 11 | i18n scaffolding; `ar` catalog compiles; Western digits | scaffolding ✓, Western digits ✓; **catalog compile DEFERRED** (gettext) |
| 12 | Audit events logged; AuditLog non-deletable; redaction | ✓ |
| 13 | CI green (lint, tests, makemigrations, check --deploy, pip-audit, secret scan) | local equivalents ✓; CI runs on first push |
| 14 | On `phase/1-foundation` + PR; `/code-review`; Critical/High fixed | branch ✓, review ✓+fixed, PR pending base branch |
| 15 | Auth security review; findings addressed | ✓ |
| 16 | PROJECT_STATUS + STATUS.md + ADRs current | ✓ |
| 17 | Accessibility basics | ✓ (labels, focus-visible, landmarks, skip-link, aria-current, status not color-only) |

Ready for Approval:
**Owner approved committing with the PostgreSQL/Docker items (DoD 1, 4, and the PG-side of
2/11/13) explicitly DEFERRED and documented above.** They must be run — locally with a
working Docker/PostgreSQL, or by CI on the first PR — before Phase 1 is considered fully
closed. No other DoD item is open.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMITTED + PUSHED — WAITING FOR USER APPROVAL OF PHASE 1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
