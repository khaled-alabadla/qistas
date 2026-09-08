# Qistas — Phase 1 Plan: Foundation

> Status: **PROPOSED — awaiting `APPROVE PHASE 1`.** Nothing has been implemented.
> Supersedes PART 5 of `QISTAS_GRILL_REVIEW.md`. Reflects all locked decisions (`docs/adr/`, `QISTAS_GRILL_REVIEW.md` PART 7).
> Rule: this plan builds **Foundation only**. No domain models. No DRF. No `django-q2`/Redis. No real dashboard. No finance logic. No client/case/hearing/document models.

---

## 1. Goal

A Dockerized, secure, RTL, i18n-ready Django shell a staff user can log into, with the authorization layer, audit seam, auth hardening, reusable UI kit, error pages, test harness, and CI baseline in place — and **zero domain entities**.

## 2. Scope (spec §82 Phase 1, refined by ADRs)

Django + PostgreSQL setup · environment config · custom `User` (email login) · authentication (login/logout/password change/reset + admin temp-password) · **RBAC foundation** (Groups + capability layer + object-scoping framework) · **minimal audit** (AuditLog + logging seam + auth events) · MFA enrollment (not enforced) · `core` app · base RTL layout · Tailwind + tokens + font · reusable UI components · permission-aware navigation · themed error pages · i18n scaffolding · Docker dev environment · CI pipeline · testing foundation · `PROJECT_STATUS.md`.

## 3. Work breakdown

### 3.0 Pre-work — decisions & ADRs (DONE, no code)
- All PART 6 decisions resolved → `QISTAS_GRILL_REVIEW.md` PART 7.
- ADR-0001 … ADR-0027 written → `docs/adr/`.
- `docs/architecture.md` written.
- Remaining work below is implementation, gated on `APPROVE PHASE 1`.

### 3.1 Repository & project scaffold
- Rename `master` → `main`; first commit adds `.gitignore` (root), `.env.example`, scaffold. Work on branch `phase/1-foundation`.
- `pyproject.toml` with pinned deps: Django 5.2 LTS, `psycopg[binary]`, `django-environ`, `whitenoise`, `django-axes`, `django-otp` (+ `qrcode`), `django-auditlog`, `django-htmx`, `pytest-django`, `factory-boy`, `faker`, `coverage`, `ruff`, `pip-audit`.
- `config/` project package; `config/settings/{base,dev,prod,test}.py` via `django-environ`.
  - `base`: installed apps, middleware order, i18n, templates, static, logging skeleton.
  - `dev`: `DEBUG=True`, console email, django-debug-toolbar.
  - `prod`: `DEBUG=False`, secure cookies, HSTS, security headers, `SECURE_SSL_REDIRECT`, etc. — `check --deploy` clean.
  - `test`: PostgreSQL, fast password hasher, deterministic settings.
- `manage.py`, `wsgi.py`, `asgi.py`.

### 3.2 Docker dev environment — ADR-0023
- `Dockerfile` (Linux, non-root, Python 3.13).
- `docker-compose.yml`: `web` (bind-mounted code), `db` (`postgres:16`), named `media` volume.
- `CreateExtension` migration: `pg_trgm`, `unaccent`.
- `README.md`: one-command onboarding (`docker compose up`), how to run tests/manage commands.

### 3.3 CI & pre-commit — ADR-0026
- `.github/workflows/ci.yml`: PG16 service; `ruff` + `ruff format --check`; `pytest` + coverage artifact; `makemigrations --check --dry-run`; `check --deploy`; `pip-audit`; `gitleaks`.
- `.pre-commit-config.yaml` mirroring the fast checks.

### 3.4 `core` app
- **Abstract models:** `TimeStampedModel` (`created_at`, `updated_at`), `AuthoredModel` (`created_by`, `updated_by`, `SET_NULL`). `SoftDeleteModel` + `SoftDeleteManager` **defined but applied to nothing yet** (ADR-0022).
- **Permission layer** (`core/permissions/`):
  - `capabilities.py` — capability constants + group→capability map + `can(user, capability)` over the union of groups. Fully unit-tested truth table.
  - `mixins.py` — `CapabilityRequiredMixin`, `require_capability` decorator; `ScopedListMixin` / `ScopedDetailMixin`.
  - `querysets.py` — `ScopedQuerySet` / `ScopedManager` base defining the `for_user()` contract + the DEBUG guard.
  - 403 handler with a themed Arabic page.
- **Numbering seam** (`core/numbering.py`): `NumberSequence` model + `next_number(scope, period="")` (transaction-safe). **No consumers in Phase 1** (ADR-0021). Concurrency test included.
- **Async seam** (`core/tasks.py`): empty module + docstring documenting the management-command/cron pattern (ADR-0005). Nothing scheduled.
- **Sensitive-fields registry** (`core/sensitive.py`): `SENSITIVE_FIELDS` set (empty in Phase 1) + logging filter that redacts listed keys (ADR-0009).
- **UI plumbing:** pagination helper, `context_processors.py` (navigation, current user capabilities), template tags/filters — `{% can %}`, `{% num %}` (bidi-safe), `badge`, `empty_state`.
- **Error views + templates:** 400 / 403 / 404 / 500 — Arabic, RTL, on-brand.
- **Landing view** (`/`): authenticated, renders a real Arabic empty-state placeholder ("لوحة التحكم قيد الإنشاء" style). The real dashboard is Phase 9.

### 3.5 `accounts` app — ADR-0004, ADR-0007, ADR-0017, ADR-0027
- **`User`** = `AbstractUser` subclass; `USERNAME_FIELD="email"`; `email` unique+required; `phone`; `must_change_password` flag; custom `UserManager`; case-insensitive email uniqueness. **`AUTH_USER_MODEL` set before the first migration.**
- **Groups:** migration creates the 5 `Group` rows. `sync_roles` management command (idempotent) owns group→permission/capability mapping; CI asserts no drift.
- **Auth flows** (Django built-ins, themed Arabic RTL): login, logout, password change, password reset (request/email/confirm/complete).
- **Admin temp-password action** (capability-gated, audited) + `must_change_password` middleware redirect.
- **`django-axes`:** lockout **by username only** (ADR: not IP), env-configurable threshold/cool-off, Arabic lockout page, admin unlock action, audited.
- **Idle-timeout middleware** (env-configurable) + project-wide `LoginRequiredMiddleware` (allowlist: auth, errors, static, healthcheck).
- **MFA** (`django-otp` TOTP): enrollment flow (QR + verify), recovery codes, per-user opt-in. Enforcement middleware present but **setting-gated OFF** (`REQUIRE_MFA=False`, `MFA_ENFORCED_GROUPS=[]`).
- **`django-auditlog` actor middleware** wired.

### 3.6 `audit` app — ADR-0020
- **`AuditLog`** model per spec §46: `actor` (`SET_NULL`), `action`, `entity_type`, `entity_id`, `object_repr` (sanitized), `changes` (JSON), `ip_address`, `user_agent`, `created_at`. Indexes: `created_at`, `(entity_type, entity_id)`, `actor`.
- **`log_event(request, action, obj=None, changes=None)`** helper.
- **Auth event receivers:** login, logout, login-failed, lockout, password change/reset, user created, group-membership change.
- **Field-diff allowlist** infrastructure (reads `core.sensitive.SENSITIVE_FIELDS`).
- **Admin:** registered read-only, delete disabled. (DB trigger → Phase 12.)

### 3.7 UI foundation — ADR-0024
- Tailwind standalone CLI build (`static/src/app.css` → `static/css/app.css`) + build script + docs; logical-utilities config, no RTL plugin.
- Design tokens (navy / slate / off-white / gray / bronze) as CSS vars + Tailwind theme.
- Self-hosted **IBM Plex Sans Arabic** (`@font-face`, swap, subset).
- `templates/base.html`: `<html lang="ar" dir="rtl">`, right sidebar, topbar, toast region, vendored HTMX + Alpine, global HTMX CSRF wiring.
- **Component kit** (`core/templates/components/`) — spec §49 list, RTL-native, `<bdi>` for numbers/IDs.
- **`/styleguide`** dev-only page rendering all components + states.
- **Navigation:** data-driven config, filtered by `capabilities`, active-state, RTL, mobile-collapsible (Alpine).

### 3.8 i18n scaffolding — ADR-0003
- `USE_I18N=True`, `LocaleMiddleware`, `LANGUAGE_CODE="ar"`, `locale/` dir.
- `FORMAT_MODULE_PATH` → Western digits, Palestine date/number conventions (ADR-0016).
- All Phase 1 strings wrapped in `gettext`. `makemessages`/`compilemessages` in the build; `ar` catalog compiled. `en` not maintained.

### 3.9 Testing foundation — ADR-0025
- `pytest.ini` / `pyproject` config; `conftest.py`; `UserFactory` + group fixtures.
- `core/tests/utils.py`: `assert_login_required`, `assert_forbidden` (403), `assert_not_found`, `assertNumQueries` wrapper, `run_concurrently`.
- **Phase 1 test suite** — see §5.

### 3.10 Project tracking & docs
- `PROJECT_STATUS.md` (spec §78) — 14 phases, Phase 1 = `COMPLETED` / `PENDING APPROVAL` when done.
- Refresh `.wolf/STATUS.md` via `/handoff`.
- `docs/architecture.md` kept current; ADR index maintained.

## 4. Deliverables checklist

- [ ] `master`→`main`; `phase/1-foundation` branch; root `.gitignore`, `.env.example`
- [ ] `pyproject.toml` (pinned), `config/settings/{base,dev,prod,test}`
- [ ] `Dockerfile`, `docker-compose.yml` (`web`+`db`+`media` volume), `README.md`
- [ ] `pg_trgm` + `unaccent` migration
- [ ] CI workflow + `.pre-commit-config.yaml`
- [ ] `core`: abstract models, permission layer (capabilities + mixins + scoped-queryset base + DEBUG guard), `NumberSequence` + `next_number`, `core/tasks.py` seam, `core/sensitive.py` + logging filter, UI plumbing, error views/templates, landing view
- [ ] `accounts`: `User` + manager, 5 groups + `sync_roles`, auth flows, admin temp-password, `django-axes` (username-only), idle-timeout + login-required middleware, MFA enrollment + setting-gated enforcement, auditlog actor middleware
- [ ] `audit`: `AuditLog`, `log_event`, auth receivers, allowlist infra, read-only admin
- [ ] UI: Tailwind build + tokens + font, `base.html`, component kit, `/styleguide`, navigation
- [ ] i18n scaffolding + `ar` catalog compiled
- [ ] Test harness + Phase 1 suite (all Tier-1, green)
- [ ] `PROJECT_STATUS.md`, refreshed `.wolf/STATUS.md`
- [ ] Phase 1 code review + auth security review; Critical/High fixed
- [ ] Phase Completion Report (spec §76)

## 5. Phase 1 test suite (Tier-1, must be green)

- **Auth:** login ok / bad password / inactive user; logout; password-change requires auth; password-reset token flow; admin temp-password action + forced change; session-cookie flags on prod settings; idle timeout expires session.
- **Lockout:** `django-axes` locks after N failures **by username**; a second username from the same IP is **not** locked; admin unlock works; lockout is audited.
- **MFA:** enrollment (QR/secret + verification); recovery codes single-use; enforcement middleware blocks when `REQUIRE_MFA=True` in a test and allows when False.
- **Capability layer:** `can()` truth table for each of the 5 groups; multi-group union; `CapabilityRequiredMixin` allow/deny; `sync_roles` idempotent + drift assertion.
- **Object-scoping framework:** against a throwaway test model — `for_user()` filters correctly; `ScopedDetailMixin` returns 403 (not 404) on denial; DEBUG guard raises when a scoped view skips `for_user()`.
- **Navigation:** items shown/hidden per capability.
- **Errors:** 400 / 403 / 404 / 500 render themed templates with `DEBUG=False`.
- **Audit:** login / logout / failed-login / user-created / group-change write `AuditLog`; `AuditLog` delete blocked (ORM + admin); a sensitive key in `changes` is redacted by the allowlist.
- **Numbering:** `next_number` basic sequence; **concurrent** allocation (threads) yields no duplicates, no lost increments.
- **i18n:** a sample view renders Arabic; digits render Western.
- **Smoke:** `manage.py check --deploy` clean on prod settings; migrations apply on a fresh PG; `pg_trgm` + `unaccent` present.

## 6. Definition of Done (Phase 1)

1. Migrations apply cleanly on an empty PostgreSQL 16.
2. All Phase 1 (Tier-1) tests pass in CI.
3. `manage.py check --deploy` clean on production settings.
4. `docker compose up` brings up the full stack; `/` requires login; login → landing → logout works.
5. MFA is enrollable; enforcement is OFF by default and provably gate-able.
6. Lockout works by username (not IP); admin unlock works.
7. Navigation filters by capability; the capability layer is centralized and unit-tested.
8. Object-scoping framework enforces 403 on denial and the DEBUG guard fires on misuse.
9. Themed 400/403/404/500 pages render with `DEBUG=False`.
10. RTL + bidi verified visually against realistic mixed Arabic / Latin / numeric content.
11. i18n scaffolding in place; all Phase 1 strings translatable; `ar` catalog compiles; Western digits confirmed.
12. Audit: auth events logged; `AuditLog` non-deletable via ORM/admin; sensitive-field redaction works.
13. CI green (lint, tests, `makemigrations --check`, `check --deploy`, `pip-audit`, secret scan).
14. Work is on `phase/1-foundation` with an open PR into `main`; `/code-review` run; Critical + High issues fixed.
15. Auth security review performed; findings addressed or explicitly deferred with justification.
16. `PROJECT_STATUS.md` present and accurate; `.wolf/STATUS.md` refreshed; every decision recorded as an ADR.
17. Accessibility basics on Phase 1 UI: labels, visible focus, semantic landmarks, contrast, status not conveyed by color alone.

**Then:** Phase Completion Report (spec §76) → **STOP** → wait for explicit approval.

**`TECHNICAL COMPLETE ≠ USER APPROVED`.**

## 7. Explicitly OUT of Phase 1 (Deferred Items)

Every domain model (Client, Case, CaseParty, Court, Hearing, Task, Deadline, Meeting, Document, Contract, Invoice, InvoiceLineItem, Payment, Expense, FeeAgreement, Notification) · the real dashboard & KPIs · DRF · reports · global search implementation (only the `pg_trgm` extension is enabled) · PDF/CSV export · notification content & scanners · demo data · `CaseConfidential` model · audit DB-trigger & partitioning · MFA org-wide enforcement · X-Accel download path · production email provider · cron jobs (none needed yet) · `django-q2`/Celery/Redis.

## 8. Risks specific to Phase 1

| Risk | Mitigation |
|---|---|
| `AUTH_USER_MODEL` set too late | It is the **first** model; no migrations before it exists. |
| RTL/bidi regressions later | Bake `<bdi>` into the component kit + `{% num %}`; visual checklist; styleguide page. |
| Capability layer becomes scattered | Single module, single `can()` entry point, truth-table tests, `sync_roles` as the only mapping owner. |
| Scoping-by-convention drift | DEBUG guard + `ScopedListMixin`/`ScopedDetailMixin` + a test that the framework raises on misuse. |
| Docker friction on Windows | `README` onboarding; all commands via `docker compose exec`; CI mirrors dev. |
| Over-building the foundation | This plan forbids domain models, DRF, dashboard, finance, async — enforced in code review. |

## 9. Open items that do NOT block Phase 1 (tracked for later phases)

Party directory & case identity fields (Phase 3) · `CaseConfidential` model (Phase 3) · optimistic-locking UI (Phases 3/8) · global search backend (Phase 2+) · rounding policy & credit-note workflow & `PaymentReversal` (Phase 8) · document download hardening / storage backend (Phase 6) · notification dedup/quiet-hours design (Phase 11) · audit DB immutability trigger (Phase 12) · production email + cron + disk encryption verification (Phase 14).
