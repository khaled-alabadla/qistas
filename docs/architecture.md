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

`core` `accounts` `audit` (P1 ✓) · `clients` (P2 ✓) · `cases` +parties+notes+timeline + `courts` (minimal) (P3 ✓) · `courts` (full) `hearings` `agenda` (P4 ✓) · `tasks` +deadlines (P5 ✓) · `documents` (P6 ✓) · `contracts` (P7 ✓) · `finance` (P8 ✓) · `dashboard` (P9 ✓) · `reports` (P10 ✓) · `notifications` (P11 ✓) · security/audit hardening (P12 ✓) · final integration + release readiness (P13 ✓ — the owner redefined P13 as the final planned phase, absorbing the originally-planned P13 quality/perf/UX pass and P14 production-readiness pass).

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

## 13. Money & finance — ADR-0032 (built in Phase 8)

- `core.money`: `Currency` `TextChoices` (ILS / JOD / USD / EUR) + `quantize` = the **one** rounding rule (`Decimal("0.01")`, `ROUND_HALF_UP`). Every stored monetary result (line totals, subtotal, tax, total) goes through it. `Decimal` end to end — **never** `float`. All arithmetic lives in `finance.services`, never a form field.
- **`finance` app — 6 models:** `FeeAgreement` · `Invoice` + `InvoiceLineItem` · `Payment` + `PaymentReversal` · `CreditNote` · `Expense`. Standard layering (models / selectors / services / thin views / forms). **No finance row is ever hard-deleted** — every model's `default_permissions` omits `delete`; `Payment` / `PaymentReversal` / `CreditNote` omit `change` too.
- **`FeeAgreement` (ADR-0013):** "رسوم القضايا" — the agreed legal fee (fixed / hourly / contingency / retainer), FK `case` PROTECT, guarded status (draft→active→completed/cancelled). **Not** an `Expense`; it records the contracted value, invoices do the billing (`Invoice.fee_agreement` optional FK).
- **`Invoice` — stored totals, frozen at issue (ADR-0011, 0012):** `invoice_number` `INV-YYYY-NNNN` **allocated at issue** (`NumberSequence`, gaps acceptable), nullable on drafts. `subtotal` / `tax_amount` / `total` are **server-computed snapshots** — `finance.services.recalculate_invoice` is the sole writer while the invoice is a `draft`, and **no code path mutates a line item or a monetary field of an issued invoice** (`_require_draft` guards every mutator; the edit view bounces an issued invoice; admin freezes issued fields). `amount_paid` is maintained only by the payment service under a row lock. A **draft** cancels directly; an **issued** invoice is corrected only by a `CreditNote` (full value ⇒ `cancelled`).
- **`متأخرة` / overdue is COMPUTED, not stored (ADR-0006):** `Invoice.is_overdue` = `status in {unpaid, partially_paid}` and `due_date < today`. It flips back the instant the invoice is paid and depends on the current date, so it is a property + `.overdue()` filter — **no cron, no stored status** (unlike a contract's `expired`, which is a genuine lifecycle end).
- **Overpayment guard (§40):** `finance.services.record_payment` opens `transaction.atomic`, takes `Invoice.objects.select_for_update()` on the invoice row, reads `credited_total − amount_paid` **and** writes `amount_paid = F("amount_paid") + amount` under that lock; `amount > outstanding` ⇒ `ValidationError`. DB `CheckConstraint amount_paid ≤ total` is the backstop. `issue_credit_note` / `reverse_payment` take the same lock, so they serialize with payments. Payments / reversals / credit notes are append-only (`PaymentReversal` voids a payment, `CreditNote` corrects an issued invoice).
- **`Expense` (ADR-0013):** money out — `EXP-YYYY-NNNN`, category, FK case+client SET_NULL, **soft-delete** (retained + audited). **Never added to an invoice `total` or a fee agreement** — reporting keeps money-in and money-out separate.
- **`Invoice.objects.with_balances()`** annotates `_credited_sum` so `outstanding` / `credited_total` need no per-row query — used on every list / card / calendar queryset.
- **Permissions:** finance is the **first domain that is NOT all-staff** (spec §98 "permission-controlled"). `finance.view` = office_manager / finance_clerk / lawyer / admin_clerk; `finance.manage` = office_manager + finance_clerk only; **paralegal has zero finance access**. Any all-staff aggregator that could surface finance data re-checks `finance.view` (`finance.selectors.calendar_items`; the case-workspace finance tab, client-profile finance cards and `case_/client_financials` are gated on `can_finance` in the view).
- Optimistic-locking tokens on draft-invoice edits (earlier "design intent") are **not** built — issued-invoice immutability + the payment row lock cover the real concurrency risks; a draft is single-clerk work. Recorded in ADR-0032 as a possible future change.

## 13a. Dashboard — ADR-0033 (built in Phase 9)

- **The dashboard *is* the landing page.** `core:landing` → `dashboard/dashboard.html`; there is no `/dashboard/` URL and no second home page. The Phase 5–8 landing widgets are folded into the dashboard's KPI row + Attention + Deadlines; `templates/core/landing.html` is deleted.
- **`dashboard` app owns no models** — `dashboard/selectors.py` is a **read/analytics layer** over the domains' own `for_user()`-scoped managers and existing selectors. `core.views.LandingView` is a thin shell (`{**build_dashboard(user)}`). No `DashboardKPI` table, no cached-count model, no second ledger (spec Phase 9 — "GOOD: count active cases from Case. BAD: a DashboardCaseKPI model").
- **Every widget is capability-gated in the query, not just the template.** `build_dashboard` reads `capabilities_for(user)` once; a widget's data is only computed if the user holds that domain's `*.view` capability. **Finance is strict (ADR-0032): a paralegal's dashboard never runs a finance query** — no financial overview, no outstanding-invoices KPI, no overdue-invoices attention block, no finance rows in "recent activity". `finance.selectors.firm_financials` also self-checks `finance.view`. Recent-activity is an allow-list of lifecycle actions grouped by their gating capability; `CASE_CONFIDENTIAL_UPDATED` is always excluded for non-`view_confidential` (ADR-0008).
- **Overdue stays computed** (ADR-0006) — every overdue figure reads a domain property / queryset method (`overdue_tasks`, `Deadline.overdue()`, `Invoice.overdue()`). The dashboard stores nothing.
- **Case analytics = CSS bar charts, no Chart.js** (`dashboard/_bars.html`, `{% widthratio %}`) — RTL-native, print-safe, no vendored asset / CSP surface / `<script>`. Chart data is server-rendered into the page, so **no unprotected chart JSON endpoint** (spec §18).
- **Financial Overview is per-currency, never summed** (ADR-0032) — `firm_financials` returns `by_currency: [{currency, invoiced, paid, credited, outstanding}]` + `expenses_by_currency`, credit-note aware, over issued invoices; the outstanding KPI is the *count* of open invoices.
- **Performance (spec Phase 9 §10):** `build_dashboard` is a bounded number of queries (~30–45), **flat** with row count, no repeated identical query (shared counts computed once in `_attention`, handed to `_kpis`; each list block fetches one bounded slice and derives its count from it). Regression-tested (`dashboard/tests/test_performance.py`). **No caching** (spec Phase 9 §11) — a wrongly-keyed cache could serve one user's finance numbers to another.
- New domain-owned selectors this phase (each with its domain): `hearings.selectors.today_hearings` / `upcoming_hearings`, `finance.selectors.overdue_invoices` / `firm_financials`.
- **Not built:** "Missing documents" (a spec §19 attention example) — there is no "required documents" concept in the domain to define it from (spec §80 — no invented definitions); a future `RequiredDocument` checklist would add it.

## 13b. Reports — ADR-0034 (built in Phase 10)

- **`reports` owns no models.** `reports/framework.py` (a typed `ReportResult` — columns / rows / per-currency totals — plus the CSV writer) + `reports/registry.py` (the catalogue) + `forms.py` + `selectors.py` (`build_<name>_report(*, user, filters)`) + thin views + templates. No `Report` / `ReportRun` / cached-result table (spec §23). Every figure is computed on request from the domains' own `for_user()`-scoped managers and existing selectors.
- **Reports implemented (spec §43):** general — `cases` (status/type/lawyer/court/priority/open-date), `clients` (census + active-case counts), `hearings` (status/court/lawyer/window), `tasks` (status/employee/priority/overdue), `deadlines` (status/overdue); financial — `revenue` (issued invoices), `payments` (net of reversals), `outstanding` (open invoices + aging buckets), `expenses` (by category), `case-financials` (per case × currency: invoiced / credited / paid / outstanding / expenses).
- **Authorization is per-domain, in the view (spec Phase 10 §6).** `registry.Report.capability` names the domain capability; `ReportView` checks `can(user, cap)` **before any query or file generation**, for the HTML page *and* the `?format=csv` endpoint. The index lists only reports the viewer can run. `reports.view` is an all-staff nav capability only (like `dashboard.view` / `agenda.view`) — not in `sync_roles`, never "see every report". **Financial reports require `finance.view` — a paralegal gets 403 on page and export** (dedicated regression test, all five).
- **Finance reuse (ADR-0032):** no total re-implemented — builders use `finance.selectors._invoice_totals_by_currency`, `Invoice.objects.with_balances()/.open()/.overdue()`, `Payment.net_amount`, `core.money.quantize`. `Decimal` end to end. **Currencies are never summed** — per-currency total blocks only; regression-tested that `1000 ILS + 500 USD` never surfaces as `1500`.
- **Date semantics (spec §8):** `date_from`/`date_to` inclusive both ends. DateField compared directly; DateTimeField (`Case.created_at`, `Hearing.scheduled_at`) → `[from 00:00, (to+1d) 00:00)` in Asia/Hebron (`reports.framework.datetime_range_filter`).
- **Filter resolution (the bug-055 rule, generalised):** the filter form carries a hidden `_run=1`. Present ⇒ real submission, cleaned values used verbatim (unchecked box / cleared date mean "off"). Absent ⇒ fresh load / pagination link / bare "export CSV" link ⇒ field `initial`s + the default 90-day window apply, so **page 2 never disagrees with page 1** and a CSV from an unfiltered page uses the same window the page showed.
- **Exports:** CSV (UTF-8 **+ BOM**, `\r\n`, Western digits, money as plain dot-decimal `Decimal`), same view + capability gate, **audited** (`AuditAction.REPORT_EXPORTED`, metadata only — slug/format/row-count/filters, never row content or figures). Server-generated filename `qistas-<slug>-<date>.csv`, no stored file, no public path. **Print** = a `@media print` stylesheet. **Server-side PDF (WeasyPrint) is deferred** — system-library / Docker-only, same class as `compilemessages`; spec §44 hedges ("where useful") and §13 says "no heavyweight PDF stack unless required"; the `ReportResult` shape already separates data from rendering.
- **Spreadsheet injection (spec §12):** `reports.framework.csv_safe` prefixes any cell/header text starting with `= + - @` or a control char with `'`.
- **Performance (spec §14):** each builder = one row query (`select_related` for every rendered FK) sliced to `MAX_ROWS = 5000` + a few summary aggregates, **no per-row query**; a capped result is flagged `truncated`. HTML paginates the in-memory capped list; query-count regression tests assert flatness across a 2→8-row population for five builders.

## 13c. Notifications — ADR-0035 (built in Phase 11)

- **`notifications` owns one model, `Notification`** — a per-user inbox row that
  is a *reference* (`entity_type` / `entity_id`, like `AuditLog`), never a copy
  of domain state. `recipient` `CASCADE` (personal data), `read_at` null = unread,
  `dedupe_key` + `UniqueConstraint(recipient, dedupe_key)` = the idempotency
  backstop. Indexes: `(recipient, read_at)`, `(recipient, -created_at)`,
  `category`. **No sensitive figures in a body** (ADR-0009) — an invoice
  notification carries the number + due date, never the amount. No delete /
  archive / retention (spec defines none, §18). Not in `sync_roles`, not
  registered with django-auditlog (an inbox row is not a domain record).
- **Generation = five idempotent reminder scans** (`notifications/generation.py`)
  wrapped by `manage.py generate_notifications` (system cron — ADR-0005; no
  worker). Categories: `hearing_upcoming` (scheduled, within
  `NOTIFY_HEARING_WITHIN_DAYS`=3), `task_overdue` (computed, ADR-0006),
  `deadline_approaching` (pending, within `NOTIFY_DEADLINE_WITHIN_DAYS`=7 **or
  past**), `invoice_overdue` (computed), `contract_expiring`
  (`expiring_soon(NOTIFY_CONTRACT_WITHIN_DAYS=30)`). The `dedupe_key` embeds the
  date that matters (`…:{scheduled_date}` / `…:{due_date}` / `…:{end_date}`) so a
  reschedule / new due date legitimately produces **one** fresh notification and
  a stable event never re-notifies ("avoid notification spam", §45). Each scan is
  `filter(dedupe_key__in=…)` + one `bulk_create(ignore_conflicts=True)` — no
  per-row, no per-recipient query.
- **Recipients are resolved to who can act, then re-checked** (spec Phase 11
  §13–14): case-linked hearing/deadline/contract → the case team
  (`assigned_lawyer` + `supporting_lawyers`); task → `assigned_to`; invoice → the
  finance-responsible set (office manager + finance clerk); fallback → office
  manager(s). Every candidate is intersected with
  `users_with_capability(<domain>.view)` **before** the row is written. Invoice
  notifications gate on **`finance.view`** — a **paralegal never receives or sees
  one** (ADR-0032). The stored `url` targets the domain detail view, which
  re-enforces the same gate — a notification is **never a side channel** around
  domain authz.
- **Lifecycle is recipient-scoped:** `Notification.objects.for_user(user)`
  (`recipient=user` only, ADR-0019) is the only path; `get_object_or_404` on it
  → **404 on URL tampering** (strict per-user siloing — 404, not the all-staff
  403). List / open / mark-one-read (`POST`) / mark-all-read (`POST`); "open"
  marks read then redirects to the (host-checked) target.
- **Badge** = `core.context_processors` gains `unread_notification_count` — one
  indexed `COUNT` (served by `(recipient, read_at)`), 0 for anonymous. Sidebar
  `الإشعارات` is a live link; topbar gets a bell + count. No new middleware.
- **Channels: in-app only** — spec §45 requires no email/SMS; `core/tasks.py`
  stays the seam if a digest is ever specified.

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

## 15a. Phase 12 hardening — ADR-0036

- **Not a feature phase.** Phase 12 re-audits Phases 1–11 end to end (authz,
  IDOR, mass assignment, finance integrity/concurrency, mixed-currency,
  document security, audit integrity, notification/report/dashboard
  authorization, N+1, DB integrity, transactions, auth/session, deployment
  config, dependencies) without trusting each phase's own self-review. No new
  app, model, or product surface.
- **Two real defects found and fixed**, each narrowly scoped with regression
  tests: (1) `finance.InvoiceUpdateView.dispatch()` returned a redirect for an
  issued invoice *before* `CapabilityRequiredMixin` ran — the sole `dispatch()`
  override in the project with an early return ahead of `super().dispatch()`
  — leaking invoice existence/issued-status to a paralegal via a 302 instead
  of a 403; fixed by moving the state guard into `get()`/`post()` (mirrors the
  already-safe `hearings._HearingActionMixin._guard_open()` pattern). (2)
  `clients.ClientForm` carried `status` on the general edit form (every other
  status-bearing domain keeps it off), letting a `clients.manage` holder
  silently archive/restore a client with no `CLIENT_ARCHIVED`/`CLIENT_RESTORED`
  audit event; fixed by dropping the field on edit + stripping `status`
  defense-in-depth in `clients.services.update_client`.
- **Everything else audited and confirmed sound, not just re-asserted**:
  mass assignment (every `ModelForm.Meta.fields` is an explicit allowlist, no
  server-controlled field anywhere), IDOR (every object resolves through
  `for_user()` + `get_object_or_404`; the two genuinely siloed boundaries —
  notifications per-recipient, finance per-capability — hold), XSS (the only
  two `|safe`/`mark_safe` uses are provably non-tainted), SQL injection (no
  raw SQL in application code), CSRF (no exemptions, every mutator is POST),
  document security (private storage re-verified to 404 at guessed `/media/`
  paths), finance concurrency (every balance-mutating function takes
  `select_for_update` on the invoice row inside `transaction.atomic`, read
  fresh from the code), audit-log immutability (model + admin both deny
  mutation), session security (Django's default login/session-rotation and
  password-reset flows, unmodified), and **`manage.py check --deploy` run
  against real `config.settings.prod` values** (not just inspected) — 0
  warnings, 1 intentionally-silenced (`axes.W006`).
- New project-wide regression file `tests/test_capability_boundary_sweep.py`:
  every finance GET/POST URL, every financial report (page + CSV), the
  dashboard's financial-overview context, the agenda's calendar events, and
  `invoice_overdue` notification generation, exercised against a paralegal at
  the HTTP layer in one place.
- PostgreSQL/Docker verification remains deferred (same environment blocker
  as every prior phase — documented in `docs/PHASE_12_REPORT.md`).

## 15b. Phase 13 — final integration & release readiness

- **Redefined by the owner as the FINAL planned phase**, absorbing the
  originally-planned Phase 13 (quality/perf/UX) and Phase 14 (production
  readiness) into one release-readiness pass. Not a feature phase — no
  product code changed; the entire diff is two new test files plus docs.
- `tests/test_integration_workflows.py` — 10 realistic, multi-step workflows
  spanning every domain boundary (client → case → hearing/task/document/
  contract/finance → notification → dashboard/report), asserting on real
  state at each step rather than "no exception raised". `tests/
  test_edge_cases.py` — 12 tests: malformed/negative/oversized URL ids
  (always 404, never 500, across 7 URL families), double-submission
  safety (invoice issue, client archive, mark-all-read), and a notification
  whose target correctly re-enforces authorization after the recipient's
  role changes.
- **Zero new bugs found** — the expected, honest result of an integration
  pass immediately following Phase 12's from-the-code re-audit on an
  unchanged codebase.
- A precision correction to Phase 12's own report: the `psycopg` driver
  *is* installed and importable in this project's venv; the real blocker is
  that no PostgreSQL **server** is reachable (no `psql`, no Docker daemon, a
  direct connection attempt to `localhost:5432` hangs) — not a missing
  driver. PostgreSQL/Docker verification remains deferred for that reason,
  documented precisely in `docs/PHASE_13_REPORT.md`.
- Final assessment: **release candidate — production-ready subject to the
  PostgreSQL/Docker environment blockers**, which are infrastructure this
  development machine cannot provide, not gaps in the application itself.

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
