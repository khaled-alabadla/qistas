# Qistas — Project Status

> Source of truth for phase progression (spec §78). One phase at a time.
> `COMPLETED ≠ APPROVED` — a phase starts only after the user says
> **APPROVE PHASE N** / **ابدأ المرحلة N**.

Current Phase: **3 — Cases** (Phases 1 & 2 approved + merged to master)

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

Branch: `phase/1-foundation` — merged to `master` (commit `4c320ec`). `master` is the GitHub default branch.

## Phase 2 — Clients
Status: **COMPLETE (technical)** — see `docs/PHASE_2_REPORT.md`
Approval: **PENDING**

`clients` app: `Client` model (individual/company, `type`-conditional name via DB
CheckConstraint + `clean()`), `client_number` `CL-YYYY-NNNN` (transaction-safe,
ADR-0021), status incl. `archived` (archive = status, never delete — ADR-0022).
CRUD (list/detail/create/update/archive/restore), client profile (overview +
notes + activity; other tabs placeheld), search (`icontains` over
name/number/phone/email/city — **never** national_id), type/status filters,
pagination. Capability gates: `clients.view` (all staff) / `clients.manage`
(office_manager, lawyer, admin_clerk) / `clients.view_sensitive` (same). `national_id`
added to `SENSITIVE_FIELDS`, gated in form + detail, masked in auditlog, excluded
from search + trigram index. `Client` registered with django-auditlog; `AuditLog`
events for create/update/archive/restore. `seed_demo_clients` command.

**Verification:**
- Tests: **59 client tests; full suite 159 pass / 0 fail / 3 skipped** (`@pytest.mark.postgres`).
- `ruff` / `ruff format` / `pip-audit` / `makemigrations --check` / `check --deploy --fail-level WARNING` clean.
- Full CRUD + search + role gates + national_id masking verified via `runserver` + SQLite.
- `/code-review` (high) + security review — Critical/High fixed.
- **CI fix:** `check --deploy` was failing `security.W009` (workflow set a 13-char
  `DJANGO_SECRET_KEY`). Fixed — the CI job now generates a fresh 86-char ephemeral
  key per run; W009 is **not** silenced; `prod.py` still requires the key from env.

**DEFERRED / UNVERIFIED — Docker/PostgreSQL environment blocker (same as Phase 1;
the session machine cannot run Docker or PostgreSQL — low RAM, network stalls):**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. `clients/migrations/0002_client_search_indexes` (trigram GIN) — never executed (PG-only, guarded).
3. The `@pytest.mark.postgres` tests (incl. client-number concurrency).
4. `docker compose` full-stack smoke.
5. `make compilemessages` (Docker-only; harmless).

Branch: `phase/2-clients` — **two commits**, pushed, **not merged**:
- `a16cc3e` `phase(2): complete clients` — the feature work
- `36a3a2d` `fix(ci): provide secure test secret key` — CI `check --deploy` fix
- (this cleanup adds a third: `fix(ci): align master workflow and phase docs`)

## Phase 3 — Cases
Status: **COMPLETE (technical)** — see `docs/PHASE_3_REPORT.md`
Approval: **PENDING**

`courts` app (minimal): `Court` model (name/type/city/is_active, `(name, city)`
unique) + admin + `seed_demo_courts` — full court CRUD is Phase 4.

`cases` app: `Case` model — `case_number` `CS-YYYY-NNNN` (transaction-safe,
ADR-0021), `internal_reference` + `court_case_number` (separate file-number vs
docket, grill P3), FK `type` (configurable `CaseType` table, 7 defaults seeded),
FK `client` (PROTECT), `assigned_lawyer` + `supporting_lawyers` M2M (through
`CaseLawyer`), FK `court` (SET_NULL), status/priority/stage, `claim_amount`
(DB CheckConstraint ≥ 0). **No `next_hearing`** — deferred to Phase 4 for clean
phase isolation.

`CaseConfidential` (1:1, `legal_notes` / `internal_notes`) — isolated row behind
`cases.view_confidential`; never selected by list/search/timeline; masked in
auditlog; edits are audit-only (no timeline entry). `CaseParty` (relationship
model — spec §27), `CaseNote` (general / correspondence, soft-deletable),
`CaseEvent` (append-only human timeline — spec §26).

Workspace detail view with real tabs (نظرة عامة / الأطراف / الملاحظات /
المراسلات / الخط الزمني) + disabled placeholders (الجلسات / المهام / المستندات /
الفواتير / المدفوعات). CRUD + status action + lawyer assignment + party add/remove
+ note add + confidential edit. List: search (`icontains` over
number/title/docket/reference/department), status/priority/type/lawyer filters,
open-only by default, pagination.

Capabilities: `cases.view` (all staff) · `cases.manage` (office_manager, lawyer,
paralegal, admin_clerk) · `cases.view_confidential` (office_manager, lawyer).
`sync_roles` extended with case + court model perms. All writes go through
`cases.services` (CaseEvent + AuditLog); `update_case` uses the freshly-fetched
diff pattern (bug-027). 7 `CASE_*` `AuditAction` members added.

**Verification:**
- Tests: **69 case/court tests; full suite 224 pass / 0 fail / 3 skipped**
  (`@pytest.mark.postgres`).
- `ruff` / `ruff format` / `pip-audit` / `makemigrations --check` /
  `check --deploy --fail-level WARNING` (prod settings) — all clean.
- HTTP smoke via `runserver` + SQLite: login → `/cases/` list → workspace tabs →
  create / edit / confidential / party / note forms all 200; seeds
  (`seed_demo_courts`, `seed_demo_cases`) run; `sync_roles --check` clean after sync.
- `/code-review` (high) — **6 findings, all fixed** with regression tests
  (edit-form drops a deactivated FK; confidential-edit audit event leaked to the
  all-staff activity panel; `get_confidential()` wrote a row + audit event on GET;
  removal actions reported success on a no-op; two minor N+1s). Self security
  review (confidential isolation, object-level authz, CSRF, mass-assignment, SQLi)
  — pass.

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL environment blocker as Phases 1–2:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. `cases/migrations/0003_case_search_indexes` (trigram GIN, `TRGM_COLUMNS ==
   SEARCH_FIELDS`) — never executed (PG-only, guarded).
3. The `@pytest.mark.postgres` tests.
4. `docker compose` full-stack smoke.
5. `compilemessages` (Docker-only; harmless).

Branch: `phase/3-cases` — one commit `phase(3): complete cases`, pushed, **not merged**.

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
