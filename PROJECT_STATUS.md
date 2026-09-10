# Qistas — Project Status

> Source of truth for phase progression (spec §78). One phase at a time.
> `COMPLETED ≠ APPROVED` — a phase starts only after the user says
> **APPROVE PHASE N** / **ابدأ المرحلة N**.

Current Phase: **11 — Notifications** (Phases 1–10 approved + merged to master)

Planning artifacts: `QISTAS_PHASE_0_ANALYSIS.md` · `QISTAS_GRILL_REVIEW.md` ·
`docs/architecture.md` · `docs/adr/0001`–`0035` · `docs/PHASE_1_PLAN.md`

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
Status: **APPROVED + merged to `master`** (PR #2, merge commit `83674a7`) — see `docs/PHASE_3_REPORT.md`
Approval: **APPROVED 2026-09-09** ("APPROVE PHASE 3")

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
Status: **APPROVED + merged to `master`** (PR #3, merge commit `9557168`) — see `docs/PHASE_4_REPORT.md`
Approval: **APPROVED 2026-09-09** ("APPROVE PHASE 4")
Design: `docs/adr/0028-hearings-calendar-and-derived-next-hearing.md`

Full `courts` CRUD (department/address/phone/notes, `CourtQuerySet` scoping +
`icontains`/trigram search, `is_active` toggle — never deleted, ADR-0022) ·
`hearings` app: timezone-aware `scheduled_at` (single source of truth; forms
split date + optional time @ 09:00, service recombines), `hearing_type` /
`status` (مجدولة/تمت/مؤجلة/ملغاة) / `room` / results, lifecycle
schedule→update/reschedule→complete/postpone/cancel — **no row ever deleted**;
complete/postpone with a next date **spawn a new scheduled row** · **`Case.next_hearing`
derived, never stored** (property + list `Subquery` annotation) · `agenda` app —
month/week/day, stdlib `calendar` (Saturday start), **no model**, a scoped
derived-event aggregator (`calendar_events`) · case-workspace الجلسات tab is now
real + next-hearing on overview/list · nav: الجلسات + المحاكم under القضايا,
المكتب→التقويم · capabilities `courts.view`(all)/`courts.manage`(office_manager),
`hearings.view`(all)/`hearings.manage`(case handlers), `agenda.view`(all);
`sync_roles` extended · 6 `HEARING_*` + 4 `COURT_*` `AuditAction`; 6 `HEARING_*`
`CaseEventType` · filtering/search/pagination throughout · RTL/Arabic-first.

**Verification:**
- Tests: **295 pass / 0 fail / 3 skipped** (`@pytest.mark.postgres`) on SQLite —
  `hearings` 39, `courts` 27, `agenda` 8, + a 16-URL end-to-end HTTP smoke.
- `ruff` / `ruff format --check` / `pip-audit` / `makemigrations --check` /
  `manage.py check` / `check --deploy --fail-level WARNING` (prod) — all clean.
- Seed chain (`seed_demo_courts` → `_clients` → `_cases` → `_hearings`, idempotent)
  + `sync_roles --check` clean after sync.
- `/code-review` (self): 4 findings fixed with regression tests (page-2 filter
  leak; past next-date; cancel-reason UX; CourtFactory location). Self security +
  performance review — pass.

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL environment blocker as Phases 1–3:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. `courts/migrations/0003_court_search_indexes` (trigram GIN,
   `TRGM_COLUMNS == SEARCH_FIELDS`) — never executed (PG-only, guarded).
3. The `@pytest.mark.postgres` tests.
4. `docker compose` full-stack smoke (equivalent verified via the Django test client).
5. `compilemessages` (Docker-only; harmless).

Branch: `phase/4-courts-hearings` — one commit `phase(4): complete courts and hearings`,
pushed, **not merged**.

## Phase 5 — Tasks + Deadlines
Status: **APPROVED + merged to `master`** (PR #4, merge commit `c52c95a`) — see `docs/PHASE_5_REPORT.md`
Approval: **APPROVED 2026-09-09** ("APPROVE PHASE 5")
Design: `docs/adr/0029-tasks-and-deadlines.md`

`tasks` app, two models: **`Task`** (title/description, `assigned_to`, optional
`case`/`client`, priority, `due_date` DateField, status new/in_progress/done/
cancelled — **no `overdue`**, ADR-0006; **soft-deletable** via `deleted_at` +
`deleted_by`) and **`Deadline`** (procedural cut-off — no assignee, `pending`/
`met`/`missed`/`cancelled`, required `due_date`, **never hard-deleted** — cancel
only, ADR-0022). "Overdue" = computed property + queryset filter, no cron.
CRUD + status actions + soft-delete (task); all through `tasks.services`
(freshly-fetched diff, `AuditLog` every mutation, `CaseEvent` when case-linked).
`tasks.selectors` (list/search/filter/pagination, `my_open_tasks`,
`overdue_tasks`, `upcoming_deadlines`, `calendar_items`). **Calendar
integration**: `agenda.selectors.calendar_events` now merges hearings + tasks +
deadlines (all-day items). **Dashboard integration**: `core:landing` shows
مهامي / مهام متأخرة / مواعيد قادمة widgets. Case workspace المهام tab is now real.
Capabilities `tasks.view` (all staff) / `tasks.manage` (office_manager, lawyer,
paralegal, admin_clerk — one pair for both models). `sync_roles` extended. 7
`TASK_*`/`DEADLINE_*` `AuditAction`; 5 `TASK_*`/`DEADLINE_*` `CaseEventType`.
Nav: المكتب → المهام / المواعيد النهائية / التقويم. `tasks/0002` trigram GIN.

**Verification:**
- Tests: **337 pass / 0 fail / 3 skipped** (`@pytest.mark.postgres`) on SQLite —
  `tasks` 47 (models/services/views/permissions/search/smoke).
- `ruff` / `ruff format --check` / `pip-audit` / `makemigrations --check` /
  `manage.py check` / `check --deploy --fail-level WARNING` (prod) — all clean.
- Seed chain (`…_courts` → `_clients` → `_cases` → `_hearings` → `seed_demo_tasks`,
  idempotent) + `sync_roles --check` clean after sync.
- `/code-review` (self): 2 findings fixed with regression tests (distinct-unsafe
  `_with_current` — also fixed the latent bug in `cases`/`hearings` forms via a
  shared `core.forms.with_current_choice`; closed-case task creation via `?case=`).
  Self security + performance review — pass.

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL environment blocker as Phases 1–4:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. `tasks/migrations/0002_task_search_indexes` (trigram GIN,
   `TRGM_COLUMNS == SEARCH_FIELDS`) — never executed (PG-only, guarded).
3. The `@pytest.mark.postgres` tests.
4. `docker compose` full-stack smoke (equivalent verified via the Django test client).
5. `compilemessages` (Docker-only; harmless).

Branch: `phase/5-tasks-deadlines` — one commit `phase(5): complete tasks and deadlines`,
pushed, **not merged**.

## Phase 6 — Documents
Status: **APPROVED + merged to `master`** (PR #5, merge commit `46dc56e`) — see `docs/PHASE_6_REPORT.md`
Approval: **APPROVED** ("APPROVE PHASE 6")
Design: `docs/adr/0030-documents-storage-and-access.md`

`documents` app: **`Document`** (name / `document_type` `DocumentCategory` /
description / `file` / `original_filename` / detected `content_type` / `size` /
`sha256`; FK `case` + `client` SET_NULL; `uploaded_by`). **Private storage** —
`documents.storage.PrivateFileSystemStorage` (`.url()` raises), a separate
`STORAGES["documents"]` entry, `upload_to` = `<yyyy>/<mm>/<uuid4><ext>` (no
user-controlled path segment), **never web-served** (no MEDIA route). The only
path to the bytes is `documents:download` — `@require_GET` + `@require_capability`
+ `for_user()` scope (404 outside scope / retired) + audited, `FileResponse`
`as_attachment` + `nosniff`. **Upload validation** (`documents.validators`) — size
≤ 25 MB, curated **magic-byte** allowlist (PDF/PNG/JPEG/GIF/TIFF/ZIP-office/OLE/
RTF/text), extension-must-agree, sha256 streamed; client `Content-Type` ignored;
no libmagic (hand-rolled, cross-platform). Metadata-only edit (the file is
immutable — versioning designed-for, not built, §36). **Retire** = soft-delete
(`deleted_at`), never hard-deleted (admin delete off, no `delete` codename).
`documents.services` (transactional, `AuditLog` every mutation with **metadata
only** — no file bytes; `CaseEvent` `DOCUMENT_ADDED`/`REMOVED` when case-linked).
Selectors (list / search / filter / pagination, `case_documents`,
`client_documents`). Capabilities `documents.view` (all staff incl. finance_clerk
— download only) / `documents.manage` (office_manager, lawyer, paralegal,
admin_clerk). `sync_roles` extended. 4 `DOCUMENT_*` `AuditAction`; 2 `DOCUMENT_*`
`CaseEventType` (`cases/0006`). Case workspace **المستندات** tab is now real;
client profile gets a documents card. Nav: **المستندات والعقود → المستندات**
(+ العقود placeholder). `documents/0002` trigram GIN. `seed_demo_documents`.

**Verification:**
- Tests: **388 pass / 0 fail / 3 skipped** (`@pytest.mark.postgres`) on SQLite —
  `documents` 51 (validators / models / services / views / permissions / smoke),
  incl. IDOR / anon / unauthorized / URL-tampering / mass-assignment / CSRF /
  method / private-file / path-traversal / disguised-executable / download-auth /
  audit / CaseEvent / retire.
- `ruff` / `ruff format --check` / `pip-audit` / `makemigrations --check` /
  `manage.py check` / `check --deploy --fail-level WARNING` (prod) — all clean.
- Seed chain + `sync_roles --check` clean.
- `/code-review` (self): 1 finding fixed with a regression test (download 500 → 404
  when the blob is missing, phantom download not audited). Self **security review —
  PASS**; self **performance review — PASS**.

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL environment blocker as Phases 1–5:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. `documents/migrations/0002_document_search_indexes` (trigram GIN,
   `TRGM_COLUMNS == SEARCH_FIELDS`) — never executed (PG-only, guarded).
3. The `@pytest.mark.postgres` tests.
4. `docker compose` full-stack smoke (equivalent verified via the Django test
   client, incl. streamed download).
5. `compilemessages` (Docker-only; harmless).
6. Real filesystem behaviour of `PrivateFileSystemStorage` under Linux prod
   (tests use `InMemoryStorage`); `FILE_UPLOAD_PERMISSIONS=0o640` unverified on a
   real FS.

Branch: `phase/6-documents` — one commit `phase(6): complete documents`,
pushed, **not merged**.

## Phase 7 — Contracts
Status: **APPROVED + merged to `master`** (PR #6, merge commit `7908beb`) — see `docs/PHASE_7_REPORT.md`
Approval: **APPROVED** ("APPROVE PHASE 7")
Design: `docs/adr/0031-contracts.md`

`contracts` app: **`Contract`** — `contract_number` `CT-YYYY-NNNN` (transaction-safe,
ADR-0021, `editable=False`), `title`, `contract_type` (`ContractType` `TextChoices`:
retainer / engagement / services / consulting / lease / employment / nda /
settlement / other), FK `client` (**PROTECT, required**), FK `case` (SET_NULL,
optional — §97), `start_date` (required) / `end_date` (nullable — open-ended
retainers), `value` `DecimalField(14,2)` (nullable) + `currency` (`Currency`
`TextChoices` ILS/JOD/USD/EUR — **a single stored amount, no arithmetic**;
Finance/invoicing is Phase 8), `status` (`ContractStatus` exactly per §37:
draft `مسودة` / active `ساري` / expired `منتهي` / cancelled `ملغى`),
`description` / `notes`. `TimeStampedModel` + `AuthoredModel`.
**No soft-delete** — legally significant (ADR-0022): `default_permissions =
("add","change","view")`, admin delete off, no `delete` codename; **"cancel" is a
terminal status**. `CheckConstraint`s: `value` null-or-`>=0`, `end_date`
null-or-`>= start_date` (mirrored in `clean()`). 6 indexes.

**Expiration** (ADR-0006): `منتهي` is a genuine status flipped by the **idempotent
`expire_contracts` management command** (`services.expire_due_contracts`) — not
auto-stored. `is_past_due` / `is_expiring_soon` / `days_until_expiry` properties +
`ContractQuerySet.expiring_soon(within_days=30)` / `.past_due()` close the gap in
the UI meanwhile. Manual transitions go through `change_contract_status`
(draft↔active↔expired reachable; `cancelled` terminal — a further transition
raises `ValidationError`, surfaced as a form message). `status` is not on the edit
form and not in the service's `EDITABLE` set.

All writes through `contracts.services` (freshly-fetched diff — bug-027;
`AuditLog` **metadata only** — `contract_number`/`title`/`contract_type`/`status`
or changed field names, never `notes`/`description`/`value` bodies, ADR-0009;
`CaseEvent` `CONTRACT_ADDED` / `CONTRACT_STATUS_CHANGED` when case-linked, not on
metadata edits). `contracts.selectors` (list / search / type+status filters /
"expiring soon" toggle / pagination — default branch hides closed rows, bug-055;
`case_contracts`, `client_contracts`, `expiring_contracts`, `calendar_items`).

**Integration:** `documents.Document` gains a nullable `contract` FK (SET_NULL,
`documents/0003`) — third scoped picker in upload/edit forms, `contract_documents`
selector + `contract_id` list filter, contract detail lists its documents.
`agenda.selectors.calendar_events` merges contract expirations (§33). `core:landing`
gets a **عقود قريبة من الانتهاء** widget (next 30 days) for `contracts.view`
holders. Case workspace **العقود** tab is real; client profile gets a contracts
card. Nav: **المستندات والعقود → العقود** is now a live link (+ **عقد جديد**).

Capabilities `contracts.view` (**all staff** incl. finance_clerk — billing context,
§21) / `contracts.manage` (**client-handler set** — office_manager, lawyer,
admin_clerk; **paralegal is view-only**, unlike tasks/documents). `sync_roles`
extended (`contracts.{view,add,change}_contract`, no `delete`). 3 `CONTRACT_*`
`AuditAction`; 2 `CONTRACT_*` `CaseEventType` (`cases/0007`). `contracts/0002`
trigram GIN (`TRGM_COLUMNS == SEARCH_FIELDS`; `notes`/`value` excluded — §4).
`seed_demo_contracts`. Shared `core.forms.scoped_case_queryset` /
`scoped_client_queryset` (extracted from `documents.forms`, code-review finding).

**Verification:**
- Tests: **439 pass / 0 fail / 3 skipped** (`@pytest.mark.postgres`) on SQLite —
  `contracts` 51 (models / services / selectors / views / permissions / smoke),
  incl. IDOR / anon / unauthorized / URL-tampering / mass-assignment
  (`contract_number` server-side, `status` not editable) / CSRF / capability
  matrix (paralegal view-only) / status-transition guard + `cancelled` terminal /
  `expire_due_contracts` idempotency + scope / agenda + landing + case-tab +
  client-card integration / `TRGM_COLUMNS == SEARCH_FIELDS` / archived-client edit
  picker / command smoke.
- `ruff` / `ruff format --check` / `pip-audit` (no known vulnerabilities) /
  `makemigrations --check` / `manage.py check` — all clean.
- `manage.py check --deploy`: the 5 warnings (HSTS / SSL-redirect / SECRET_KEY /
  secure cookies) are **test-settings only** — `config/settings/prod.py` sets all
  of them; a real prod-settings run needs `DJANGO_SECRET_KEY` + PostgreSQL (see
  deferred).
- `/code-review` (high): 5 findings — 1 real bug fixed (`seed_demo_contracts` not
  `@transaction.atomic` → `select_for_update` outside a transaction on PG,
  buglog **bug-076**), 1 latent exposure fixed (landing task-widget sections now
  guarded independently of the contracts widget), 3 DRY cleanups applied (shared
  scoped-queryset helpers; redundant status guard removed). Self **security
  review — PASS** (no HIGH/MEDIUM). Self **performance / N+1 review — PASS**
  (all list/detail/calendar paths `select_related`; pagination present; no N+1
  introduced; the repeated `can()` per-request pattern is pre-existing and in
  scope for the Phase 12 N+1 sweep, ADR-0010).

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL environment blocker as Phases 1–6:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. `contracts/migrations/0002_contract_search_indexes` (trigram GIN,
   `TRGM_COLUMNS == SEARCH_FIELDS`) — never executed (PG-only, guarded).
3. The `@pytest.mark.postgres` tests.
4. `docker compose` full-stack smoke (equivalent verified via the Django test client).
5. `compilemessages` (Docker-only; harmless).
6. `manage.py check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY`
   env + PostgreSQL). `prod.py` sets HSTS / SSL-redirect / secure cookies /
   env-supplied `SECRET_KEY`.

**Known limitations:**
- Contract metadata (title / dates / value) stays editable in any status — ADR-0031
  freezes only `status` (guarded transition) and the delete path, not the whole
  record. A future "freeze on `expired` / `cancelled`" is a small service-layer
  tightening if the office asks; it is not an ADR-0012-style requirement (that is
  invoices/finance).
- Contract reminders / "expiring" notifications are **Phase 11** (a scan over
  `expiring_soon()`); the landing widget + calendar are the Phase 7 surface.
- `value` establishes `Decimal` + `currency` with **no** finance logic — no
  totals, invoicing, or fee roll-ups (Phase 8, additive).

Branch: `phase/7-contracts` — one commit `phase(7): complete contracts`,
pushed, **not merged**. Parent: `46dc56e` (Phase 6 merge, PR #5).

## Phase 8 — Finance
Status: **APPROVED + merged to `master`** (PR #7, merge commit `32e350b`) — see `docs/PHASE_8_REPORT.md`
Approval: **APPROVED** ("APPROVE PHASE 8")
Design: `docs/adr/0032-finance.md` (building on ADR-0011, 0012, 0013)

`finance` app — 6 models, `Decimal` end to end (`core.money.quantize`, 2dp
ROUND_HALF_UP), all arithmetic server-side, no hard delete of any row.

- **`FeeAgreement`** ("رسوم القضايا" = agreed legal fee, NOT an expense — ADR-0013):
  `FA-YYYY-NNNN`, FK `case` PROTECT, `fee_type` (fixed / hourly / contingency /
  retainer) with the matching money field validated, guarded status
  (draft→active→completed/cancelled).
- **`Invoice`** + **`InvoiceLineItem`**: `INV-YYYY-NNNN` **assigned at issue**
  (ADR-0011, gaps OK), FK client PROTECT / case+fee_agreement SET_NULL. `discount`
  + `tax_rate` inputs; `subtotal` / `tax_amount` / `total` are **server-computed
  snapshots, frozen at issue** (ADR-0012) — `recalculate_invoice` is the sole
  writer while draft, no code path mutates an issued invoice. `amount_paid`
  maintained only by the service under a row lock. Line items CASCADE (aggregate
  child), added/removed only while draft via `CaseParty`-style action views.
  `is_overdue` **computed, never stored** (ADR-0006). Draft → cancel directly;
  issued → corrected only by a credit note.
- **`Payment`** (immutable, `add/view` only): `PMT-YYYY-NNNN`, FK invoice PROTECT.
  **Overpayment guard (§40):** `record_payment` holds `select_for_update` on the
  invoice row across the outstanding-balance read + `amount_paid` write;
  `amount > outstanding` → `ValidationError`; `amount_paid <= total`
  `CheckConstraint` backstop. **`PaymentReversal`** for voids (Σ ≤ payment).
- **`CreditNote`** (`add/view` only): `CN-YYYY-NNNN`, against an issued invoice
  (Σ ≤ total); a full-value note flips the invoice to `cancelled`.
- **`Expense`** (money out, standalone — never in an invoice/fee total):
  `EXP-YYYY-NNNN`, category, `spent_on`, FK case+client SET_NULL, **soft-delete**.

Capabilities: **`finance.view`** (office_manager / finance_clerk / lawyer /
admin_clerk — **paralegal has NO finance access**, §12/§98 — the first
non-all-staff domain) / **`finance.manage`** (office_manager + finance_clerk
only). `sync_roles` extended — **no `delete` codename anywhere in finance**.
13 `*_*` `AuditAction` (metadata only, ADR-0009); 4 `CaseEventType` (`cases/0008`).
`finance/0002` trigram GIN.

Integration: `المالية` nav section live · `core:landing` "المبالغ المستحقة"
widget · case workspace real **المالية** tab · client profile real ملخص مالي +
invoice/payment cards · `agenda.calendar_events` merges invoice due dates
(re-checks `finance.view` since the agenda is all-staff) · `core.money.py` shared ·
`Invoice.objects.with_balances()` annotation kills the outstanding-balance N+1 ·
`seed_demo_finance`.

**Verification:**
- Tests: **529 pass / 0 fail / 4 skipped** (`@pytest.mark.postgres`) on SQLite —
  **+90 finance tests** (models / fee agreements / invoices / payments / expenses
  / permissions / smoke): server-side totals, forged-total/number/status rejection,
  issued immutability, credit-note full/partial, **overpayment rejected +
  `@postgres` concurrent-overpayment** + SQLite sequential guard, reversal, IDOR /
  URL-tampering / mass-assignment, capability matrix (paralegal = no access),
  agenda-calendar finance-leak guard, invoice-list flat-query-count N+1 guard,
  `TRGM==SEARCH_FIELDS`.
- `ruff` / `ruff format --check` / `pip-audit` (no vulns) / `makemigrations
  --check` / `manage.py check` — all clean.
- `manage.py check --deploy`: 5 warnings, **test-settings only** (`prod.py` sets
  HSTS / SSL redirect / secure cookies / env `SECRET_KEY`).
- Self **security review — PASS** (no Critical/High); self **performance / N+1
  review — PASS**.

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL blocker as Phases 1–7:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. Trigram migrations on real PG (incl. `finance/0002`) — guarded, PG-only.
3. The 4 `@pytest.mark.postgres` tests — incl.
   `test_concurrent_payments_cannot_overpay` (the one that actually exercises
   `select_for_update`; a sequential guard test covers SQLite).
4. `docker compose` full-stack smoke.
5. `compilemessages` (Docker-only; harmless).
6. `check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY` + PG).

**Known limitations:** overdue is a computed flag not a stored `متأخرة` status
(ADR-0006 — flips back on payment); a discount set before line items is stored
as-entered (`total` never goes negative; `issue_invoice` rejects `discount >
subtotal`); no optimistic-locking token on draft edits (design intent, deferred).
Reports = Phase 10, dashboard = Phase 9, notifications = Phase 11 — **no Phase 9+
functionality introduced** (verified).

Branch: `phase/8-finance` — one commit `phase(8): complete finance`, pushed,
**not merged**. Parent: `7908beb` (Phase 7 merge, PR #6).

## Phase 9 — Dashboard + Analytics
Status: **APPROVED + merged to `master`** (PR #8, merge commit `21ff0ea`) — see `docs/PHASE_9_REPORT.md`
Approval: **APPROVED** ("APPROVE PHASE 9")
Design: `docs/adr/0033-dashboard.md`

**The dashboard *is* the landing page.** `core:landing` → `dashboard/dashboard.html`;
no `/dashboard/` URL, no second home page. The Phase 5–8 landing widgets are
folded into the dashboard's KPI row + Attention + Deadlines; `templates/core/
landing.html` deleted.

`dashboard` app — **owns no models**. `dashboard/selectors.py` is a
**read/analytics layer** over the domains' `for_user()`-scoped managers +
existing selectors; `core.views.LandingView` is a thin shell
(`{**build_dashboard(user)}`). No `DashboardKPI` table, no cached-count model,
no second ledger.

- **KPIs (§18):** القضايا النشطة · جلسات اليوم · المهام المتأخرة · القضايا العاجلة
  · إجمالي العملاء · عقود قريبة من الانتهاء · الفواتير المستحقة (count — finance-gated).
- **Today's hearings (§19):** time / case / client / court / lawyer / status,
  still-scheduled, in the office tz.
- **Attention required (§19):** overdue tasks · overdue deadlines · hearings
  next 7d · high-priority open cases · expiring contracts · overdue invoices
  (finance-gated). Empty blocks hidden; a true empty state when nothing.
- **Case analytics (§19):** by status / priority / type / lawyer — **CSS bar
  charts, no Chart.js** (RTL-native, print-safe, no vendored asset / CSP
  surface / `<script>`; no chart JSON endpoint — data is server-rendered).
- **Financial overview (§19):** **per-currency**, credit-note aware, over issued
  invoices — `firm_financials(user)`; ILS + USD shown separately, **never
  summed**. Reuses `Invoice.objects.overdue()/.open()/.with_balances()` +
  `core.money.quantize`.
- **Recent activity (§19):** an allow-list of domain lifecycle audit actions
  grouped by the capability that gates each group; `CASE_CONFIDENTIAL_UPDATED`
  always excluded for non-`view_confidential` (ADR-0008).
- **Upcoming deadlines / recently-updated cases** sections.

**Authorization:** the page is every authenticated user's home; **each widget's
data is only computed if the user holds that domain's `*.view` capability**
(`build_dashboard` reads `capabilities_for(user)` once). **Finance is strict
(ADR-0032): a paralegal's dashboard never runs a finance query.** A group-less
user gets a valid empty dashboard. New domain-owned selectors:
`hearings.selectors.today_hearings`/`upcoming_hearings`,
`finance.selectors.overdue_invoices`/`firm_financials`.

**Verification:**
- Tests: **560 pass / 0 fail / 4 skipped** (`@pytest.mark.postgres`) on SQLite —
  **+31 dashboard tests** (selectors / permissions / performance / views):
  KPI correctness, computed-overdue, per-currency + credit-note-aware
  financials, **paralegal sees no finance anywhere** (KPIs / attention /
  overview / recent-activity — the critical regression), capability matrix,
  group-less-user safe-empty, confidential-action exclusion, **flat
  query-count** (8→24 rows identical), full-render + every-role smoke.
- `ruff` / `ruff format --check` / `pip-audit` (no vulns) / `makemigrations
  --check` (no changes — `dashboard` has no models) / `manage.py check` — clean.
- `manage.py check --deploy`: 5 warnings, **test-settings only** (`prod.py` sets
  HSTS / SSL / secure cookies / env `SECRET_KEY`).
- Self **security review — PASS** (no Critical/High; the dashboard is *more*
  locked down than the page it replaced — per-domain gating added). Self
  **performance / N+1 review — PASS** (bounded, flat query count; shared counts
  computed once; every list slice `select_related`; **no caching** — a
  wrongly-keyed cache could serve one user's finance numbers to another).
- `/code-review high` — findings addressed (see `docs/PHASE_9_REPORT.md`).

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL blocker as Phases 1–8:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. The 4 `@pytest.mark.postgres` tests (finance concurrency, numbering, trigram).
3. `docker compose` full-stack smoke.
4. `compilemessages` (Docker-only; harmless).
5. `check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY` + PG).

**Known limitations:** "Missing documents" (a §19 attention example) is **not**
implemented — no "required documents" concept exists in the domain to define it
from (spec §80). Case analytics are CSS bars, not an interactive JS chart
(deliberate — ADR-0033).

Branch: `phase/9-dashboard` — one commit `phase(9): complete dashboard`, pushed,
**not merged**. Parent: `32e350b` (Phase 8 merge, PR #7).

## Phase 10 — Reports
Status: **COMPLETE (technical)** — see `docs/PHASE_10_REPORT.md`
Approval: **PENDING**
Design: `docs/adr/0034-reports.md`

`reports` app — a **read/export layer over the Phase 1–9 domains; owns no
models** (`framework.py` typed `ReportResult` + CSV writer · `registry.py`
catalogue · `forms.py` · `selectors.py` builders · thin views · templates).
`ReportView` renders one report as a paginated HTML table or, with
`?format=csv`, an audited CSV. No JSON/chart endpoint.

**Reports (spec §43):** general — `cases` · `clients` · `hearings` · `tasks` ·
`deadlines`; financial — `revenue` · `payments` · `outstanding` (with aging) ·
`expenses` · `case-financials`.

**Authorization (spec Phase 10 §6):** every report gated on its **domain**
capability in the view, **before any query or file generation** (HTML + CSV).
Financial reports require **`finance.view`** — a **paralegal gets 403 on the
page and the export** (critical regression test, all five). `reports.view` is an
all-staff nav capability only (like `dashboard.view`) — not in `sync_roles`,
never "see every report"; the index lists only runnable reports.

**Finance (ADR-0032):** no total re-implemented — reuses
`_invoice_totals_by_currency`, `Invoice.objects.with_balances()/.open()/
.overdue()`, `Payment.net_amount`, `core.money.quantize`; `Decimal` end to end.
**Currencies never summed** — per-currency total blocks only.

**Exports:** CSV (UTF-8 + BOM, `\r\n`, Western digits, `csv_safe` formula-
injection guard on every cell + header, server-generated filename, no stored
file/public path). **Print** = `@media print` stylesheet. **Server-side PDF
(WeasyPrint) DEFERRED** — Docker/system-library only, spec §44 hedges,
§13 says no heavyweight PDF stack unless required. Every CSV export →
`AuditAction.REPORT_EXPORTED` (metadata only).

**Filter resolution (bug-055 generalised):** hidden `_run=1` marks a real
submission (cleaned values verbatim); absent (fresh load / pagination / bare CSV
link) → field `initial`s + default 90-day window, so page 2 never disagrees
with page 1.

**Nav:** `التقارير` between `المالية` and `الإشعارات`.

**Verification:**
- Tests: **~689 pass / 0 fail / 4 skipped** (`@pytest.mark.postgres`) on SQLite
  — **+129 reports tests** (`test_access` / `test_filters` / `test_general_reports`
  / `test_financial_reports` / `test_exports` / `test_performance` / `test_views`):
  login + per-report capability matrix + **paralegal-vs-financial-report 403
  (page & export)** + groupless-user-safe-empty + unknown-slug-404 + IDOR/tamper;
  reversed/garbage/unknown-choice filter rejection + date boundary inclusivity +
  combined filters + **page-2-keeps-default (bug-055)** + CSV-matches-page-window;
  report correctness (open-only, active-case counts, computed overdue, status
  counts, ordering); Decimal + credit-note-aware + **per-currency separation
  (never `1500`)** + aging buckets + net-of-reversal; CSV headers/rows/values +
  **formula-injection neutralised** + BOM + server filename + audit-metadata-only
  + auth-before-generation; **flat query count** (2→8 rows identical, ≤ 15);
  every report renders full + empty.
- `ruff` / `ruff format --check` / `pip-audit` (no vulns) / `makemigrations
  --check` (no changes — `reports` has no models) / `manage.py check` — clean.
- `manage.py check --deploy`: 5 warnings, **test-settings only** (`prod.py` sets
  HSTS / SSL / secure cookies / env `SECRET_KEY`).
- Self **security review — PASS** (no Critical/High). Self **performance / N+1
  review — PASS** (bounded, flat; `MAX_ROWS` cap; no per-row query).
- `/code-review high` command is **not available in this environment**
  (`.claude/commands/` has only `designqc` / `handoff` / `reframe` /
  `security-audit`); a rigorous **self code-review** was done instead —
  consistent with Phases 4–9. Findings fixed pre-commit (filter-resolution /
  window consistency, audit-metadata source, aging-bucket accuracy note).

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL blocker as Phases 1–9:**
1. Full suite on **PostgreSQL 16** (SQLite only).
2. The 4 `@pytest.mark.postgres` tests.
3. `docker compose` full-stack smoke; report/export tests on PostgreSQL.
4. `compilemessages` (Docker-only; harmless).
5. `check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY` + PG).
6. **Server-side PDF export** — deferred by design (ADR-0034 §7).

**Known limitations:**
- No PDF export (browser print-to-PDF is the interim); no saved report
  definitions; no trend / period-over-period analysis; no scheduled delivery
  (Phase 11). Reports are capped at `MAX_ROWS = 5000` rows — a truncated result
  is flagged and asks the user to narrow filters.
- Aging-bucket sub-totals in the outstanding report are computed from the
  displayed (capped) rows; the headline per-currency outstanding is exact.

Branch: `phase/10-reports` — merged to `master` (PR #9, merge commit `ac1b500`).

## Phase 11 — Notifications
Status: **COMPLETE (technical)** — see `docs/PHASE_11_REPORT.md`
Approval: **PENDING**
Design: `docs/adr/0035-notifications.md`

`notifications` app — **one model, `Notification`**: a per-user inbox row that is
a *reference* (`entity_type` / `entity_id`, like `AuditLog`), never a copy of
domain state. `recipient` `CASCADE`, `category` (5-value `TextChoices`), `title`
/ `body` (short server-generated Arabic — §99), `url`, `dedupe_key`, `read_at`
(null = unread). **`UniqueConstraint(recipient, dedupe_key)`** + indexes
`(recipient, read_at)` / `(recipient, -created_at)` / `category`. **No sensitive
figures in a body** (ADR-0009) — invoice notifications carry the number + due
date, never the amount. No delete / archive / retention (spec defines none).
Not in `sync_roles`; not registered with django-auditlog.

**Generation = 5 idempotent reminder scans** (`notifications/generation.py`)
wrapped by `manage.py generate_notifications` (system cron — ADR-0005, no
worker; `--only <cats>` supported). `seed_demo_notifications` is the same under
a seed-chain name. Categories + `dedupe_key`:
`hearing_upcoming` (`…:{scheduled_date}`, `NOTIFY_HEARING_WITHIN_DAYS`=3) ·
`task_overdue` (`…:{due_date}`, computed ADR-0006) ·
`deadline_approaching` (`…:{due_date}`, `NOTIFY_DEADLINE_WITHIN_DAYS`=7 **or
past**) · `invoice_overdue` (`…:{due_date}`, computed) ·
`contract_expiring` (`…:{end_date}`, `expiring_soon(NOTIFY_CONTRACT_WITHIN_DAYS=30)`).
Date-keyed → a reschedule / new due date makes **one** fresh notification, a
stable event never re-notifies. Each scan = `filter(dedupe_key__in=…)` + one
`bulk_create(ignore_conflicts=True)` — no per-row / per-recipient query.

**Recipients** resolved to who can act (case team = `assigned_lawyer` +
`supporting_lawyers`; task = `assigned_to`; invoice = office manager + finance
clerk; fallback = office manager(s)), then intersected with
`users_with_capability(<domain>.view)` **before** any row is written.
`invoice_overdue` gates on **`finance.view`** — a **paralegal never receives or
sees a finance notification** (ADR-0032, dedicated regression tests). The stored
`url` targets the domain detail view, which re-enforces the same gate — a
notification is never a side channel around domain authz.

**Lifecycle** recipient-scoped: `Notification.objects.for_user(user)`
(`recipient=user` only) is the only path; `get_object_or_404` on it → **404 on
URL tampering** (strict per-user siloing). List (paginated, all/unread +
category filter) · open (`GET` → mark read → host-checked redirect to target) ·
mark-one-read (`POST`) · mark-all-read (`POST`). `_safe_next` /
`url_has_allowed_host_and_scheme` on every redirect.

**Nav:** `core.context_processors` gains `unread_notification_count` (one
indexed `COUNT`, 0 for anonymous). Sidebar `الإشعارات` is a live link with a
count badge; topbar gets a bell. **Channels: in-app only** (spec §45 requires no
email/SMS).

**Verification:**
- Tests: **741 pass / 0 fail / 4 skipped** (`@pytest.mark.postgres`) on SQLite —
  **+51 notification tests** (`test_models` / `test_services` / `test_generation`
  / `test_command` / `test_views` / `test_context`): unique-constraint +
  recipient scoping + unread filter; `notify` / `bulk_notify` idempotency +
  in-batch dedupe; every trigger's recipient + target + idempotency +
  reschedule-produces-one-fresh; **`invoice_overdue` reaches finance users only,
  paralegal gets ZERO, no amount in body**; command safe-to-rerun + `--only`;
  anon-redirect + IDOR 404 + cross-user mark no-op + `GET` rejected + offsite
  `next`/`url` rejected; badge is per-user + a single COUNT.
- `ruff` / `ruff format --check` / `pip-audit` (no vulns) / `makemigrations
  --check` / `manage.py check` — all clean.
- `manage.py check --deploy`: the same 5 warnings, **test-settings only**
  (`prod.py` sets HSTS / SSL / secure cookies / env `SECRET_KEY`).
- Self **security review — PASS** (no Critical/High): IDOR (404 on tamper),
  recipient isolation, finance side-channel (recipient rule + capability
  intersection + target-view re-check), XSS (auto-escaped bodies, no `|safe`),
  no mass assignment (server-generated rows only), forged read-state impossible
  (scoped queryset). Self **performance review — PASS**: each scan is flat (one
  events query + one prefetch + two recipient-set queries + two write queries);
  badge is one indexed COUNT.
- `/code-review high` command is **not available in this environment** (same as
  Phases 4–10); a rigorous **self code-review** was done — findings fixed
  pre-commit (deadline `now` timezone handling; N+1 avoided by reading the
  `supporting_lawyers` prefetch cache).

**DEFERRED / UNVERIFIED — same Docker/PostgreSQL blocker as Phases 1–10:**
1. Full suite on **PostgreSQL 16** (SQLite only). Expect ~741 pass, 0 skipped.
2. The 4 `@pytest.mark.postgres` tests. **Phase 11 adds one migration**
   (`notifications/0001_initial`) — portable ORM only, no PG-specific DDL.
3. `docker compose` full-stack smoke; `generate_notifications` against PostgreSQL.
4. `compilemessages` (Docker-only; harmless).
5. `check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY` + PG).

**Known limitations:**
- §45's wishlist categories that are **not** built this phase: "case assignment",
  "document uploaded", "important case update" — the Phase 11 scope list is
  reminder-shaped; `notifications.services.notify` is the seam for event-driven
  categories later (no schema change needed).
- Notifications surface only as often as cron runs (the dashboard + calendar are
  the real-time surfaces).
- `bulk_create(ignore_conflicts=True)` return count can slightly over-report on
  a genuine concurrent-scan race (the pre-filter makes the window tiny); the
  rows themselves are still correct (unique constraint).

Branch: `phase/11-notifications` — one commit `phase(11): complete notifications`,
pushed, **not merged**. Parent: `ac1b500` (Phase 10 merge, PR #9).

## Phase 12 — Audit + Advanced Security (hardening)
Status: NOT STARTED
Approval: N/A

## Phase 13 — Quality + Performance + UX (hardening)
Status: NOT STARTED
Approval: N/A

## Phase 14 — Production Readiness
Status: NOT STARTED
Approval: N/A
