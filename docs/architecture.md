# Qistas — Architecture

> Living document. Reflects decisions **locked 2026-09-08** (see `docs/adr/`).
> Companion documents: `QISTAS_PROJECT_SPEC.md` (product source of truth), `QISTAS_GRILL_REVIEW.md` (adversarial review + decision log), `docs/PHASE_1_PLAN.md` (current phase).
> Status: **pre-implementation.** Nothing in this document has been built yet.

---

## 1. Product & scope

Qistas (قِسطاس) is an Arabic-first, RTL, server-rendered **law-practice management system** for a single law office in **Palestine**: clients → cases (central object) → hearings / tasks / deadlines / documents / contracts → finance (invoices / payments / expenses / fee agreements) → dashboard / reports / notifications, wrapped in strict server-side authorization, audit logging, and data-integrity guarantees.

Built strictly **one phase at a time** (14 phases). `COMPLETED ≠ APPROVED`.

## 2. Tenancy — ADR-0001

**Single-tenant. One office per deployment.** No `Office`/tenant foreign key on any model. Multi-tenancy, if ever needed, is a deliberate future migration (add discriminator + tenant-aware scoping + data partitioning) — explicitly **not** pre-built.

## 3. Technology stack

| Layer | Choice | Notes |
|---|---|---|
| Language / framework | Python 3.13, **Django 5.2 LTS** | LTS horizon covers the 14-phase build |
| Database | **PostgreSQL 16** | `pg_trgm` + `unaccent` extensions; ICU collation for Arabic — ADR-0023 |
| Templating / UI | Django Templates + **Tailwind (logical utilities)** + HTMX + Alpine.js + Chart.js | No SPA — ADR-0024 |
| REST API | **None** | No DRF until a real external consumer exists (spec §88) |
| Async / scheduled | **None in v1** — management commands + system cron | No worker, no Redis — ADR-0005 |
| Auth hardening | `django-axes`, `django-otp` (TOTP) | ADR-0017, ADR-0026 |
| Audit | `django-auditlog` + explicit event logging | ADR-0020 |
| Dev / CI | Docker Compose (`web` + `db`); GitHub Actions | ADR-0023, ADR-0026 |
| Tests | `pytest-django`, `factory_boy`, `faker[ar]`, `coverage` | Run on PostgreSQL — ADR-0025 |
| Lint / format | `ruff` (+ `ruff format`) | pre-commit + CI |

## 4. Package & app layout — ADR-0018

```
qistas/
  manage.py  pyproject.toml  .env.example  .gitignore
  docker-compose.yml  Dockerfile
  config/                     # project package (settings/, urls, wsgi, asgi)
    settings/{base,dev,prod,test}.py
  core/                       # Phase 1 — abstract models, permission layer, UI kit, errors, numbering seam
  accounts/                   # Phase 1 — custom User, auth flows, groups, MFA
  audit/                      # Phase 1 — AuditLog + logging seam
  templates/  static/  locale/  docs/
```

- **Phase 1 creates only `core`, `accounts`, `audit`.** Every later phase creates its own app.
- `core` (not `common`). `agenda` will be the calendar app (the name `calendar` shadows the Python stdlib) — ADR-0018.
- Per-app structure: `models.py`, `forms.py`, `views.py` (thin), `urls.py`, `admin.py`, `templates/<app>/`, `tests/`.
- `selectors.py` (permission-scoped read queries) and `services.py` (multi-step transactional writes) are added **only where justified** — not a mandatory layer on trivial CRUD (spec §10, §298). The one always-on cross-cutting pattern is permission-scoped querysets (§6 below).

### App roadmap (informational — not built until each phase is approved)

`core` `accounts` `audit` (P1 ✓) · `clients` (P2 ✓) · `cases` +parties+notes+timeline + `courts` (minimal) (P3 ✓) · `courts` (full) `hearings` `agenda` (P4 ✓) · `tasks` +deadlines (P5 ✓) · `documents` (P6 ✓) · `contracts` (P7 ✓) · `finance` (P8) · `dashboard` (P9) · `reports` (P10) · `notifications` (P11) · security/audit hardening (P12) · quality/perf/UX hardening (P13) · production readiness (P14).

### Clients (P2) — implemented notes

- `Client` (individual/company) — `type`-conditional name enforced by a DB `CheckConstraint` **and** `Model.clean()`. `client_number` = `CL-YYYY-NNNN` via `core.numbering` (ADR-0021). `status` includes `archived`; **archive is a status change, never a delete** (ADR-0022) — no `deleted_at` on `Client`.
- **Visibility:** every authenticated staff member sees every client (ADR-0008). `Client.objects.for_user()` returns all rows for an authed user, none for anonymous; a missing pk is **404** (there is no per-row siloing to hide). Capabilities: `clients.view` (all 5 groups), `clients.manage` (office_manager, lawyer, admin_clerk), `clients.view_sensitive` (same as manage).
- **`national_id`** is registered in `core.sensitive.SENSITIVE_FIELDS`; excluded from `SEARCH_FIELDS`, from the trigram index, from the list template; gated out of the form and detail view for users without `clients.view_sensitive`; masked in the django-auditlog diff. `registration_number` is UI-gated only (company registration ≠ personal PII).
- Layering: `clients/services.py` (transactional create/update/archive/restore, each emitting a readable `AuditLog` event) + `clients/selectors.py` (`client_list`, permission-scoped). django-auditlog's `LogEntry` holds the detailed field diff; the client profile's Activity tab reads `AuditLog`.
- Search: `icontains` OR over name/number/phone/email/city — portable across SQLite and PostgreSQL. `clients/migrations/0002` adds trigram GIN indexes, guarded to PostgreSQL only.

### Cases (P3) — implemented notes

- **`Case`** — central object. `case_number` = `CS-YYYY-NNNN` via `core.numbering` (ADR-0021, `editable=False`, gaps OK). Separate `internal_reference` (office file no.) and `court_case_number` (docket) — grill P3. FK `type` → configurable `CaseType` table (7 Arabic defaults seeded by a data migration); FK `client` **PROTECT**; `assigned_lawyer` (SET_NULL) + `supporting_lawyers` M2M through `CaseLawyer`; FK `court` (SET_NULL). `status` / `priority` / `stage`; `claim_amount` with a DB `CheckConstraint` (≥ 0). **No `next_hearing`** — that lands with `hearings` in P4 to keep the phase boundary clean. Closing is a `status` change, never a delete (ADR-0022); `CaseNote` is soft-deletable (`deleted_at`).
- **Visibility:** every authenticated staff member sees every case (ADR-0008). `Case.objects.for_user()` = all rows for an authed user, none for anonymous; a missing pk is **404**. Capabilities: `cases.view` (all 5 groups), `cases.manage` (office_manager, lawyer, paralegal, admin_clerk), `cases.view_confidential` (office_manager, lawyer).
- **`CaseConfidential`** — 1:1 side model holding `legal_notes` / `internal_notes` (both in `core.sensitive.SENSITIVE_FIELDS`). Never selected by the list selector, search, or timeline; only fetched when `cases.view_confidential`; masked in the django-auditlog diff. Edits go through `services.set_confidential`, which writes an **`AuditLog` event only — no `CaseEvent`** so the staff-visible timeline never hints at privileged content.
- **`CaseParty`** — relationship model for opponents / counsel / representatives (spec §27), optionally linked to a `Client` or `User`. **`CaseEvent`** — append-only human-readable timeline (spec §26); every `services` mutation records one, and later phases (hearings, tasks, documents) will emit events too.
- Layering: `cases/services.py` (all transactional writes — create/update/status/party/note/lawyer/confidential, each emitting `CaseEvent` + `AuditLog`; `update_case` diffs against a **freshly-fetched** row — bug-027) + `cases/selectors.py` (`case_list` with filters, `case_parties` aggregator). Detail view is a tabbed workspace; tabs for not-yet-built modules render as disabled placeholders.
- Search: `icontains` OR over case_number / title / court_case_number / internal_reference / department. `cases/migrations/0003` adds trigram GIN indexes (`TRGM_COLUMNS == SEARCH_FIELDS`), guarded to PostgreSQL.
- **`courts`** app ships **minimal** in P3 — `Court` (name / type / city / is_active, `(name, city)` unique) is only what a `Case` FK + picker need. Full court management UI + address/phone/notes fields are P4.

### Contracts (P7) — implemented notes — ADR-0031

- **`Contract`** — `contract_number` = `CT-YYYY-NNNN` via `core.numbering` (ADR-0021, `editable=False`, gaps OK). `title` · `contract_type` (fixed `TextChoices`) · FK `client` **PROTECT, required** · FK `case` **SET_NULL**, optional (§97) · `start_date` (required) / `end_date` (nullable) · `value` `DecimalField(14,2)` + `currency` (`TextChoices`) — **one stored amount, no arithmetic**; finance/invoicing is P8 and builds on top additively · `status` (`draft` / `active` / `expired` / `cancelled` — spec §37 verbatim) · `description` / `notes`. `TimeStampedModel` + `AuthoredModel`. DB `CheckConstraint`s: `value` null-or-`≥ 0`, `end_date` null-or-`≥ start_date` (mirrored in `clean()`).
- **Never deleted** (ADR-0022, same class as `Hearing` / `Deadline`): `default_permissions = ("add","change","view")`, admin delete off, no `delete` codename. **"cancel" is a terminal `status`** — no delete path in the app.
- **Expiration is a real status, not a computed flag** (contrast task/deadline "overdue"): `expired` is flipped by the **idempotent `expire_contracts` management command** (`contracts.services.expire_due_contracts`) — the ADR-0005 / §12 "contract-expiry scan" pattern; running it is a P14 concern, the command + tests exist now. Computed `is_past_due` / `is_expiring_soon` / `days_until_expiry` + `ContractQuerySet.expiring_soon()` / `.past_due()` (ADR-0006) close the gap in the list / calendar / landing widget meanwhile. Manual transitions go through `change_contract_status` (`draft↔active↔expired` reachable, `cancelled` terminal); `status` is not on the edit form and not in the service's `EDITABLE` set.
- **Visibility:** every authed staff member sees every contract (ADR-0008). Capabilities: `contracts.view` (**all 5 groups** incl. finance_clerk — value + term are billing context, §21), `contracts.manage` (**the client-handler set** — office_manager, lawyer, admin_clerk; **paralegal is view-only**, unlike documents/tasks — a contract is an engagement instrument with a client).
- Layering: `contracts/services.py` (transactional writes — `AuditLog` **metadata only** per ADR-0009, never `notes`/`description`/`value` bodies; `CaseEvent` `CONTRACT_ADDED` / `CONTRACT_STATUS_CHANGED` when case-linked, not on metadata edits; `update_contract` diffs a freshly-fetched row — bug-027) + `contracts/selectors.py` (`contract_list` with filters + "expiring soon" toggle + pagination, `case_contracts`, `client_contracts`, `expiring_contracts`, `calendar_items`).
- Search: `icontains` OR over `contract_number` / `title` / `description` — **`notes` and `value` are excluded** (§4). `contracts/migrations/0002` adds trigram GIN indexes (`TRGM_COLUMNS == SEARCH_FIELDS`), guarded to PostgreSQL.
- **`Document.contract`** — the spec §34 "a document may belong to a Contract" seam lands here: a nullable `contract` FK on `documents.Document` (SET_NULL, `documents/0003`), wired into the upload/edit forms (third scoped picker), `documents.selectors` + `documents.services`. `agenda.selectors.calendar_events` gains contract-expiry events (§33, the ADR-0028 one-function extension point). `core:landing` gains a "عقود قريبة من الانتهاء" widget (P9 owns the full dashboard). Shared `core.forms.scoped_case_queryset` / `scoped_client_queryset` (extracted from `documents.forms`).

## 5. Authentication — ADR-0004, ADR-0017, ADR-0027

- Custom `User` = **`AbstractUser` subclass**. `USERNAME_FIELD = "email"` — **work email is the login identifier**. `username` is not used as the identifier. `employee_code` is a documented extension point (nullable, unique-if-present) for later.
- `email` unique, required. Additional fields: `phone`, `first_name`, `last_name`, `is_active`, `is_staff` (= "can open Django admin" only), timestamps.
- `django-axes` lockout **by username (email) only**, never by IP (whole office is one NAT IP). Env-configurable threshold/cool-off, Arabic lockout page, admin unlock action, audited.
- Sliding **idle-timeout** middleware (env-configurable). Project-wide `LoginRequiredMiddleware` (allowlist: auth pages, error pages, static, health check).
- **MFA:** `django-otp` + TOTP. **Enrollable in Phase 1**, enrollment UI shipped, per-user opt-in. Enforcement middleware exists but is **setting-gated and OFF** by default. Global/role enforcement is decided in Phase 12.
- **Password reset:** Django's email flow (console backend in dev; real provider in Phase 14) **plus** an admin "issue temporary password (force change on next login)" action for users without usable email.

## 6. Authorization (RBAC) — ADR-0007, ADR-0008, ADR-0019

Four enforced layers; the UI is **never** a security boundary (spec §15).

1. **Authentication gate** — login-required middleware.
2. **Group-based capability layer** — **Django Groups are the source of truth.** Five groups seeded (`office_manager`, `lawyer`, `paralegal`, `admin_clerk`, `finance_clerk`); **a user may belong to multiple groups.** A centralized, testable capability map (`core.permissions.capabilities`) resolves `can(user, "cases.view")` over the union of the user's groups. It drives both the permission-aware navigation (cosmetic) and `CapabilityRequiredMixin` on views (enforced). An idempotent `sync_roles` management command owns the group→permission/capability mapping (CI asserts no drift); migrations only create the Group rows.
3. **Object-level authorization** — an explicit `Model.objects.for_user(user)` scoped queryset, used in **every** list, detail, foreign-key dropdown, autocomplete and search. `ScopedListMixin` / `ScopedDetailMixin` require it and raise otherwise; a DEBUG-only assertion catches unscoped renders; a permission-matrix test enforces it. **Denial → HTTP 403** with a clear Arabic message (not 404 — v1 has no strict siloing, and 404 hurts operability).
4. **Sensitive-field gating** — internal/legal notes and financial figures are gated **independently** of case visibility. Case confidential fields live on a `CaseConfidential` 1:1 side model (built in Phase 3) so a field that was never selected cannot leak into CSV, HTMX partials, `__str__`, audit diffs, search snippets, or error pages. A single `case.for_display(user)` projection is the only rendering path.

**v1 case visibility:** all staff (all groups) can see all office cases in lists and aggregates. Editing, and the sensitive fields above, are group- and assignment-gated. **No** strict lawyer-to-assigned-case siloing.

## 7. Data & database — ADR-0021, ADR-0022, ADR-0023, ADR-0025

- **PostgreSQL 16.** Extensions `pg_trgm`, `unaccent` enabled via `CreateExtension` migrations in Phase 1. ICU collation for Arabic-aware sorting on text columns where it matters.
- **Money:** `Decimal(14, 2)` everywhere, arithmetic server-side, DB `CheckConstraint`s, `transaction.atomic()` for multi-row writes. `currency` field on every financial model (default from settings). Rounding: `ROUND_HALF_UP`, 2 dp, round only final tax + grand total. *(All finance details are design intent — built in Phase 8.)*
- **`on_delete` policy (ADR-0022):** `CASCADE` **only within an aggregate root** (e.g. `InvoiceLineItem → Invoice`, `CaseParty → Case`). `PROTECT` / `SET_NULL` across roots and for anything legally significant. Never `CASCADE` into `Case`, `Hearing`, `Invoice`, `Payment`, `Document`, `Contract`, `AuditLog`.
- **Soft-delete & archival (ADR-0022):** soft-delete applies to a **small named set** only (initially `Task`, `Note`, `Document`; revisit per phase). "Archive" for `Case` / `Client` is a **status value**, not deletion. True deletion is a rare admin action requiring reassignment. Reference numbers use **full** unique indexes — never reused; a soft-deleted row keeps its number.
- **Reference numbers (ADR-0021):** a `NumberSequence(scope, period, last_value)` table; `select_for_update` + increment **in the same transaction** as the insert. **Gaps are acceptable** (no gap-free legal numbering in v1). `invoice_number` is assigned at **issue**, not on draft. A real concurrency test is mandatory. *(Framework scaffold may exist in `core` in Phase 1 with no consumers; first real use is Phase 2.)*
- **Constraints over app code:** unique / check / FK / not-null constraints are declared at the DB level and mirrored in `Model.clean()` where useful (spec §56).
- **Indexing:** based on real query patterns (spec §58). `national_id` and equivalents are **not** trigram-indexed and **not** in global search (ADR-0009).

## 8. Audit logging — ADR-0020

- `django-auditlog` for automatic model-change capture, with its **actor middleware** (thread-local for actor identity only — the standard, well-tested approach). Models are registered as each phase adds them.
- Explicit `log_event(request, action, obj=None, changes=None)` for non-ORM events: login, logout, failed login, lockout, password change/reset, user created, group-membership change, document download (Phase 6), permission change, report export (Phase 10).
- **Field-diff allowlist:** sensitive fields (`internal_notes`, `legal_notes`, `national_id`, financial figures, document contents) are logged as *"changed"* with **no** old/new values. `object_repr` must not embed sensitive text.
- Audit-detail views enforce the **same** object/field permissions as the underlying record. "Viewed audit log" is itself an audited event.
- `AuditLog`: `actor` `on_delete=SET_NULL`; **no ORM/admin delete**; indexes on `created_at`, `(entity_type, entity_id)`, `actor`. A DB-level `BEFORE DELETE/UPDATE` trigger and monthly partitioning are **deferred to Phase 12** (the model is designed not to fight them).

## 9. Sensitive data handling — ADR-0009

- **No application-level field encryption in v1.** Confidentiality rests on: PostgreSQL / disk-volume / object-storage encryption (deployment concern, documented in Phase 14), plus secure application handling.
- `national_id`, and any field of equivalent sensitivity, is **highly sensitive**: optional, never written to logs, never surfaced in UI/exports/search unless strictly required, permission-restricted, not trigram-indexed, excluded from global search.
- **Extension point:** a pluggable encrypted-field wrapper can be introduced later (e.g. `pgcrypto` / `django-cryptography`) without a schema redesign — sensitive fields are kept few and centrally listed (`core.sensitive.SENSITIVE_FIELDS`).

## 10. Internationalization — ADR-0003, ADR-0016

- **i18n-ready from day 1.** `USE_I18N = True`, `LocaleMiddleware`, `locale/` directory, all human-facing strings via `gettext` (`_()`, `{% translate %}`, `{% blocktranslate %}`). Model `TextChoices` use translatable labels.
- **Ships `ar` only.** `LANGUAGE_CODE = "ar"`. An `en` catalog stub exists but is not a Phase 1 deliverable. Phase 1 UI is Arabic-first.
- **Western digits** (`0-9`) for IDs, references, dates, and monetary values. `FORMAT_MODULE_PATH` set explicitly so locale defaults never switch to Arabic-Indic digits. Arabic UI text remains RTL.
- Palestine locale conventions (currency, date format, first day of week). **Hijri date display is deferred** (jurisdiction rules kept extensible — ADR-0002).

## 11. UI / RTL foundation — ADR-0024

- `<html lang="ar" dir="rtl">`. **Tailwind 3.4+ native logical utilities** (`ps-*`, `pe-*`, `ms-*`, `me-*`, `text-start/end`, `start-*`/`end-*`). **No RTL plugin.**
- **Bidi isolation:** all numbers, identifiers, money, dates, emails, phone numbers are wrapped in `<bdi>` via a `{% num %}` / component helper — mixed Arabic/Latin content must not scramble (spec §204).
- Self-hosted **IBM Plex Sans Arabic** (`font-display: swap`, subset, `unicode-range`).
- Design tokens: deep navy / dark slate / warm off-white / neutral gray / subtle bronze — restrained, per spec §5.
- Reusable component kit in `core` (spec §49 list). Dev-only `/styleguide` page.
- Permission-aware navigation from a data-driven config, filtered by the capability layer, mobile-collapsible (Alpine).
- Themed error pages: 400 / 403 / 404 / 500, Arabic, RTL.

## 12. Async & scheduled work — ADR-0005

**No worker, no broker, no Redis in v1.** Time-based features (overdue recomputation *if it ever needs materializing*, hearing/task/invoice/contract reminders, contract-expiry scans) are implemented as **idempotent Django management commands** invoked by **system cron** in the deployment environment (documented in Phase 14).

**Seam for the future:** a thin `core/tasks.py` module of plain callables. Each management command is a one-line wrapper around a callable. Introducing `django-q2` or Celery later means changing the wrappers, not the callers. Phase 1 creates the empty `core/tasks.py` and documents the pattern; it schedules nothing (Phase 1 has no time-based feature).

## 13. Money & finance — design intent (built in Phase 8)

- `Decimal(14,2)`, `currency` field, `ROUND_HALF_UP` (round final tax + total only).
- **Issued invoices are immutable (ADR-0012).** Once an invoice leaves `draft`, its line items and monetary fields are frozen. Corrections use a **credit-note / correction** mechanism — the full workflow is a Finance-phase deliverable, not Phase 1.
- Payments immutable; `PaymentReversal` for voids/corrections (Finance phase).
- `select_for_update` on the invoice row for payment writes; overpayment rejected (spec §40). Optimistic-locking token on financial (and case) edit forms.
- **`FeeAgreement` (ADR-0013):** "رسوم القضايا" is an agreed legal fee with the client (fixed / hourly / contingency / retainer), attached to a case. **Not** an `Expense`. Structure finalized in the Finance phase.

## 14. Testing strategy — ADR-0025

Tiered policy:

- **Tier 1 — blocks the phase:** authentication; authorization (capability + object-level + URL-tampering); money math & payment rules; reference-number concurrency; document access control; audit-write assertions.
- **Tier 2 — should have:** CRUD happy/validation paths; filters; search scoping.
- **Tier 3 — nice to have:** UI states, pagination edges.

`pytest-django` + `factory_boy` + `faker` (`ar_AA` locale, realistic Palestinian names — spec §61) + `coverage`. **Tests run on PostgreSQL** (never SQLite — the schema uses PG-specific constraints/extensions). `assertNumQueries` guards on heavy list/detail pages as they are built. A `run_concurrently` helper backs the numbering test.

## 15. Development, CI & VCS — ADR-0023, ADR-0026

- **Dev runs in Docker** (`docker compose up`: `web` + `db`). The app is **never** run natively on Windows — parity with Linux production (libmagic, file paths, collation, future WeasyPrint) matters. Windows is the editor host only; commands run via `docker compose exec`.
- **CI (GitHub Actions):** PostgreSQL 16 service container; `ruff` + `ruff format --check`; `pytest` + coverage artifact; `python manage.py makemigrations --check --dry-run`; `python manage.py check --deploy` (prod settings); `pip-audit`; `gitleaks`.
- `.pre-commit-config.yaml` mirrors the fast CI checks.
- **VCS:** rename `master` → `main`. Work on `phase/N-<name>` branches → PR into `main` → CI + `/code-review` gate the merge → tag `phaseN-approved` after explicit user approval.

## 16. Process — ADR-0010

One phase at a time. **Security, authorization, audit, testing, accessibility, and performance are part of the Definition of Done of every relevant phase** — never postponed. Phases 12 and 13 are **hardening / review passes** that deepen and verify what earlier phases already established, not the first time these concerns are addressed. Each phase ends: implement → test → code review → security review → fix → Phase Completion Report (spec §76) → **STOP** → wait for explicit `APPROVE PHASE N` / `ابدأ المرحلة N`.

## 17. Deferred features & decisions (tracked, not lost)

| Item | Deferred to | Source |
|---|---|---|
| Multi-tenancy / `Office` FK | Future major migration if needed | ADR-0001 |
| Conflict-of-interest / privilege checking | Post-v1 feature | ADR-0014 |
| Client portal (client login) | Post-v1 feature | ADR-0015 |
| Application-level field encryption | Extension point ready; decide later | ADR-0009 |
| Hijri date display | Jurisdiction extensibility | ADR-0002 |
| `django-q2` / Celery / Redis | Only if a real requirement appears | ADR-0005 |
| MFA global/role enforcement | Phase 12 | ADR-0017 |
| Audit DB-trigger + partitioning | Phase 12 | ADR-0020 |
| Gap-free legal invoice numbering | Only if law/accounting later requires it | ADR-0011 |
| Credit-note / payment-reversal workflow | Phase 8 (Finance) | ADR-0012 |
| `FeeAgreement` structure | Phase 8 (Finance) | ADR-0013 |
| Office-wide Party directory (standalone) | Phase 4+ — P3 ships per-case `CaseParty` | grill X9 |
| Payment/case optimistic-locking UI | Phases 3 / 8 | grill F5 |
| Real-time / digest notification design | Phase 11 | grill (notifications) |
| Global search backend (`pg_trgm`) | Phase 2+ | grill C5 |
| X-Accel-Redirect download path | Phase 6 (if perf requires) | grill D5 |
| Case identity fields (`internal_reference` vs `court_case_number`) | ✓ Phase 3 | grill P3 |
