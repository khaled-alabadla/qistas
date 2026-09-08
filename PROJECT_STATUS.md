# Qistas — Project Status

> Source of truth for phase progression (spec §78). One phase at a time.
> `COMPLETED ≠ APPROVED` — a phase starts only after the user says
> **APPROVE PHASE N** / **ابدأ المرحلة N**.

Current Phase: **1 — Foundation**

Planning artifacts: `QISTAS_PHASE_0_ANALYSIS.md` · `QISTAS_GRILL_REVIEW.md` ·
`docs/architecture.md` · `docs/adr/0001`–`0027` · `docs/PHASE_1_PLAN.md`

---

## Phase 1 — Foundation
Status: **COMPLETE (technical) — 1 verification step DEFERRED** — see `docs/PHASE_1_REPORT.md`
Approval: **PENDING**

Django + PostgreSQL scaffold · Docker dev + CI · custom `User` (email login) ·
authentication (login/logout/password change/reset + admin temp-password) ·
RBAC foundation (Groups + capability layer + object-scoping framework) ·
minimal append-only audit (AuditLog + event logging + auth receivers) · MFA
enrollment (enrollment not forced; completion mandatory once enrolled) · `core`
app · RTL base layout + Tailwind + IBM Plex Sans Arabic · reusable component kit ·
permission-aware navigation · themed error pages · i18n scaffolding · Tier-1 tests.

**Verification:**
- Tests: **100 pass / 0 fail / 2 skipped**. The 2 skipped are `@pytest.mark.postgres`
  (`pg_trgm`/`unaccent` present after migrate; `NumberSequence` concurrency with real
  row locking) — they run only on a PostgreSQL backend.
- `ruff` clean · `ruff format` clean · `pip-audit` clean · `makemigrations --check`
  clean · `manage.py check --deploy` clean on prod settings.
- Full auth/authz flow verified via `runserver` + SQLite (login → landing → logout;
  office-manager `/settings/` → 200; lawyer `/settings/` → 403; MFA QR renders; themed 404).
- `/code-review` (8 findings) + auth security review — all Critical/High fixed with
  regression tests.

**DEFERRED / UNVERIFIED (environment could not run PostgreSQL or Docker this session —
~0.28 GB free RAM, network stalling on large pulls):**
1. The full test suite has **not** been run against **PostgreSQL 16** (only SQLite).
2. `core/migrations/0002_postgres_extensions` (`CREATE EXTENSION pg_trgm, unaccent`)
   has **not** executed (it is vendor-guarded → no-op on SQLite).
3. The 2 `@pytest.mark.postgres` tests are **unverified**.
4. `docker compose build` + `docker compose up` (full-stack smoke) — **not run**.
5. `make compilemessages` (needs GNU gettext, Docker-only) — **not run** (harmless:
   ships `ar`, source strings are Arabic).

**Exact remaining PostgreSQL checks (run before Phase 1 is considered fully done):**
```
docker compose build
docker compose run --rm web python manage.py migrate            # -> 0002 extensions apply
docker compose run --rm web pytest                              # -> 102 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/                # -> 302 /accounts/login/
```

Branch: `phase/1-foundation` — one commit `phase(1): complete foundation`, pushed, **not merged**.

## Phase 2 — Clients
Status: NOT STARTED
Approval: N/A

## Phase 3 — Cases
Status: NOT STARTED
Approval: N/A

## Phase 4 — Hearings + Courts + Calendar
Status: NOT STARTED
Approval: N/A

## Phase 5 — Tasks + Deadlines
Status: NOT STARTED
Approval: N/A

## Phase 6 — Documents
Status: NOT STARTED
Approval: N/A

## Phase 7 — Contracts
Status: NOT STARTED
Approval: N/A

## Phase 8 — Finance
Status: NOT STARTED
Approval: N/A

## Phase 9 — Dashboard + Analytics
Status: NOT STARTED
Approval: N/A

## Phase 10 — Reports
Status: NOT STARTED
Approval: N/A

## Phase 11 — Notifications
Status: NOT STARTED
Approval: N/A

## Phase 12 — Audit + Advanced Security (hardening)
Status: NOT STARTED
Approval: N/A

## Phase 13 — Quality + Performance + UX (hardening)
Status: NOT STARTED
Approval: N/A

## Phase 14 — Production Readiness
Status: NOT STARTED
Approval: N/A
