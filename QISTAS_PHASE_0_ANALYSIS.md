# Qistas — Phase 0 Analysis (Pre‑Implementation)

> Status: **PROPOSAL — awaiting your review.** No application code has been written.
> Date: 2026-09-08
> Scope of this document: repository assessment, spec grilling, architecture proposal,
> domain model proposal, RBAC strategy, phased plan, Phase 1 detailed plan, risks, open questions.

---

## 1. Current repository assessment

**Verdict: greenfield. No application code exists.**

| Area | Finding |
|---|---|
| Git | `origin` = `https://github.com/khaled-alabadla/qistas.git`. Branch **`master`**, **no commits yet**. Harness expects `main`. |
| App code | None. No `manage.py`, no `pyproject.toml`/`requirements.txt`, no Django project, no migrations, no venv, no Docker Compose, no CI. |
| Present | `QISTAS_PROJECT_SPEC.md` (the spec), multi‑assistant config (`.claude/`, `.cursor/`, `.opencode/`, `.agents/`), OpenWolf tooling (`.wolf/`), stub `AGENTS.md` / `GEMINI.md` / `CLAUDE.md`. |
| Root hygiene | **No root `.gitignore`** (only `.wolf/.gitignore`). Must add one before first commit (venv, `.env`, `__pycache__`, `/media`, `staticfiles`, Node modules). |
| OpenWolf state | Empty/pending: `anatomy.md` unscanned, `buglog.json` empty, `cerebrum.md` near‑empty, `STATUS.md` is the template. |
| Toolchain (verified) | Python **3.13.14**, Node **25.6**, Docker **29.5**, PostgreSQL client **not installed** (Docker can host the DB). Windows 11 / PowerShell. |
| `/grill-me` | Not wired for Claude Code in this repo (the `grilling` skill referenced by `.agents/skills/grill-me` is not registered). Grilling below was performed manually in its spirit. |

**Implication:** Phase 1 genuinely starts from zero. Every foundational decision is still open, which is the right time to make them deliberately.

---

## 2. Understanding of the product (condensed)

Qistas is an **Arabic‑first, RTL, server‑rendered** law‑practice management system for a law office: clients → cases (the central object) → hearings/tasks/deadlines/documents/contracts → finance (invoices/payments/expenses/fees) → dashboard/reports/notifications, all wrapped in **strict server‑side authorization**, **audit logging**, and **data‑integrity guarantees** (Decimal money, DB constraints, no casual cascade deletes).

Stack is fixed by the spec: **Django monolith + PostgreSQL + Django Templates + Tailwind + HTMX + Alpine + Chart.js**, DRF only if a real API consumer appears. Development is **strictly phase‑gated** (14 phases): plan → implement → test → review → fix → report → **STOP** → wait for explicit approval. `COMPLETED ≠ APPROVED`.

---

## 3. Grilling — ambiguities, contradictions, missing decisions

### 3.1 Foundational (block Phase 1)

1. **Tenancy model — the single most important decision.** The spec says "law offices" (plural) and "a law office" but never states whether Qistas is **single‑tenant** (one deployment per office) or **multi‑tenant SaaS** (many offices in one database). This changes every model (tenant FK everywhere), every query scope, every permission check, backups, and onboarding. The role list tops out at "مدير المكتب" (office manager), not a platform owner, and demo data describes one office. → **Recommendation: single‑tenant now, written tenancy‑ready** (see §4). Needs your confirmation.

2. **Jurisdiction / country is unspecified.** Arabic could mean SA / JO / EG / AE / PS… This drives: national‑ID and commercial‑registration formats & validation, court hierarchy and naming, VAT/tax model and rate, invoice legal requirements, data‑retention obligations, and whether a **Hijri calendar** is expected. → Need the target country (or countries).

3. **Language scope.** Arabic‑only UI, or bilingual (ar/en) via `gettext`? → **Recommendation: build `gettext`‑ready from day 1, ship `ar` only.** Confirm whether English is ever required.

4. **Currency & tax.** Single currency or multi? Is "tax" on invoices a single configurable VAT rate, multiple rates, or line‑level? Rounding rules? → **Recommendation: single configurable currency + single configurable VAT rate for v1.** Confirm.

5. **Time‑based work needs a scheduler, but the stack has no async worker.** "Hearing approaching", "task overdue", "invoice overdue", "contract expiring", plus email for password reset and (later) PDF export, all need something to run on a schedule. The spec's stack (§9) lists no Celery/Redis/queue. → **Recommendation: OS cron + Django management commands for the MVP**, with a documented seam to move to `django-q2` (DB‑backed, no Redis) if volume grows. Pick this now to avoid rework in Phase 5/11. Confirm.

6. **"Overdue" is both a stored status and a computed rule — contradiction.** §31 lists `متأخرة` as a Task status value; §32 says overdue must be *derived* server‑side from `due_date < today AND status != completed`. If it is stored, something must flip it (cron); if it is derived, it should not be in the status enum. Same tension for invoices (§39 lists `متأخرة`). → **Recommendation: stored status = `{new, in_progress, done, cancelled}` (+ invoice `{draft, unpaid, partial, paid, cancelled}`); "overdue" is a computed property + list filter + dashboard bucket, not a stored value.** This diverges from the spec's literal enum — flag for approval.

7. **Django admin in production?** Is the office manager a Django‑admin user, or does everything happen in a purpose‑built in‑app UI? → **Recommendation: Django admin = superuser/developer only (never the office‑manager role); office manager gets in‑app management screens.** `is_staff` stays "can open Django admin", `role` drives the app. Confirm.

8. **Minimal audit in Phase 1?** Full audit hardening is Phase 12, but login/logout/failed‑login and "permission changed" need logging from the start, and retro‑fitting a diff‑capturing audit layer across 12 phases of models is expensive. → **Recommendation: build the `AuditLog` model + a logging seam (helper + auth signals) in Phase 1**, expand coverage per phase, harden in Phase 12. Confirm.

9. **Email provider for password reset.** Flow can be built in Phase 1 with the console backend; the real provider (SES / SMTP / Postmark…) can wait for Phase 14 — but confirm that's acceptable.

10. **Repo branch & remote.** Keep `master` or rename to `main` (harness default, and GitHub's default)? First commit should also add the root `.gitignore` and `.env.example`.

11. **CI now or later?** → **Recommendation: minimal GitHub Actions in Phase 1** (ruff + black check, `pytest`, `manage.py check --deploy` on prod settings). Cheap insurance across 14 phases. Confirm.

12. **RBAC editability.** Fixed capability sets per role (only group *membership* is admin‑editable) vs fully admin‑editable per‑group permissions vs per‑user overrides? §46 audits "Permission changed", implying at least some runtime editing. → **Recommendation: fixed capability sets per role in code for v1; admin can move users between roles; per‑user overrides deferred.** Confirm.

13. **Test framework.** `pytest-django` + `factory_boy` vs Django `TestCase`. → **Recommendation: `pytest-django` + `factory_boy` + `coverage`.** Confirm.

14. **Dev database via Docker Compose** (Postgres in a container, app native on Windows) acceptable? Docker Desktop is installed and working.

### 3.2 Domain decisions (needed before the relevant phase, not Phase 1)

| # | Question | Phase | Recommendation |
|---|---|---|---|
| 15 | Do lawyers see **all** office cases (list/read) or **only their assigned + supporting** cases? The §15 URL‑tampering example implies strict siloing, but most offices let lawyers see all cases. | 3 | Confirm. Default assumption: lawyers see all office cases in lists; object policy still blocks non‑members from editing and from internal notes. |
| 16 | "مساعد محامي" (paralegal) scope: cases of their supervising lawyer(s)? cases where they hold a task? Needs a supervisor link or a rule. | 3/5 | Add `paralegal.supervisors` M2M; paralegal sees supervisors' cases. |
| 17 | Field‑level visibility: which roles can see `legal_notes` / `internal_notes` (Case) and financial figures? §92 data‑minimisation. | 3/8 | Lawyers + office manager see legal/internal notes; finance clerk sees finance + limited case view; admin clerk sees logistics, not legal notes. |
| 18 | "رسوم القضايا" (case fees) — is this a **fee agreement** (retainer / hourly / contingency / fixed) that generates invoices, or just an expense category? Undefined. | 8 | Model a `FeeAgreement` per case; invoices reference it. Needs product input. |
| 19 | Invoice **line items** now or single‑amount invoices? §39 has no items; Phase 8 says "if required". Retrofitting is painful. | 8 | Build `InvoiceLineItem` from the start; `subtotal`/`total` computed from items. |
| 20 | Invoice `paid_amount` / `remaining_amount`: **stored** (fast, can drift) or **computed** from payments (correct, more queries)? | 8 | `paid_amount` = cache maintained inside the Payment transaction, guarded by a DB `CheckConstraint (0 <= paid_amount <= total)`; `remaining` = computed property. |
| 21 | **Deadlines** — own model (statute‑of‑limitations / appeal windows: critical, non‑completable, alarmed) or a Task flag? §33 shows them on the calendar; Phase 5 label is "TASKS + DEADLINES". | 5 | Dedicated `Deadline` model — legal deadlines are not chores. |
| 22 | "Next hearing" is stored on **both** `Case.next_hearing` and `Hearing.next_hearing_date` — two sources of truth. | 4 | `Case.next_hearing` = derived (earliest future `scheduled` hearing), cached; completing a hearing with a next date **creates a new Hearing row** rather than storing a loose date. |
| 23 | Calendar shows "Meetings" and "Deadlines" but there is no Meeting model in the module list. | 4 | Lightweight `Meeting` (title, datetime, participants, optional case/client) + `Deadline` (from #21); calendar is a union selector, no new "event" table. |
| 24 | Case tab "المراسلات" (correspondence) — a distinct entity (logged letters/emails) or a note subtype? | 3 | Start as a `Note` with a `kind` field; promote later if needed. |
| 25 | Numbering: `case_number`, `client_number`, `invoice_number`, `contract_number` — auto or manual? format? per‑year reset? uniqueness scope? race safety? | 2+ | Configurable prefix + year + zero‑padded sequence (e.g. `C‑2026‑0001`), generated inside a transaction with `select_for_update` on a counter row. |
| 26 | Documents: storage backend (local vs S3‑compatible), max size, allowed types, download mechanism (stream through Django vs nginx `X‑Accel‑Redirect`). | 6 | Private storage; allowlist `pdf, doc/docx, xls/xlsx, jpg, png`; 25 MB default (env); magic‑byte validation; download only via authorized audited view. |
| 27 | Reports "PDF where useful" — Arabic RTL PDF is genuinely hard. | 10 | WeasyPrint (best Arabic/RTL, heavier deps) vs deferring PDF and shipping CSV + print‑stylesheet first. Decide at Phase 10. |
| 28 | Global search backend: `icontains` vs Postgres FTS (weak Arabic stemming) vs `pg_trgm` + `unaccent`. | 2+ | `pg_trgm` GIN indexes + permission‑scoped querysets. |
| 29 | Soft‑delete / archive matrix — which entities may be hard‑deleted, which soft‑deleted, which only archived by status? §57 is a principle, not a table. | per‑phase | Draft matrix in §4.6; confirm per phase. |
| 30 | Client portal — do clients ever log in? Never mentioned. | — | Assume **no client portal**. Confirm. |
| 31 | MFA/2FA — expected for legal confidentiality? Not in §14. | 1 or 12 | Scaffold `django-otp` (TOTP) in Phase 1, enforce/roll out in Phase 12. Confirm timing. |
| 32 | Time tracking / billable hours and **client trust/escrow accounting** — common in legal PM, absent here. | — | Assume **out of scope**. Confirm (both are large if later required). |
| 33 | Timezone: single fixed (e.g. `Asia/Riyadh`) vs per‑user. | 1 | `USE_TZ=True`, single configurable `TIME_ZONE`. Confirm. |
| 34 | Courts appear in **both** Phase 3 and Phase 4 scope. | 3/4 | Minimal `Court` (name/type/city) in Phase 3 for the Case FK; full Court management UI in Phase 4. Confirm. |

---

## 4. Proposed Django architecture

### 4.1 Runtime & libraries

| Concern | Choice | Rationale |
|---|---|---|
| Django | **5.2 LTS** | Supports Python 3.13; LTS support horizon fits a 14‑phase build. |
| DB driver | `psycopg[binary]` 3.x | Current standard. |
| Settings | `django-environ`, split `settings/{base,dev,prod,test}.py`, `.env.example` | §65. |
| Static | **WhiteNoise** | No separate static server needed early. |
| CSS | **Tailwind standalone CLI** (no Node app), `tailwindcss-rtl`/logical utilities | Avoids a Node build pipeline in the Django repo. |
| JS | HTMX + Alpine.js **vendored** into `static/vendor/` (not CDN) | Offline‑safe, CSP‑friendly. |
| Auth hardening | `django-axes` (lockout), `django-otp` (TOTP, scaffold) | §14, §54. |
| Async (MVP) | **management commands + OS cron**; seam for `django-q2` | Stack has no worker; keep it simple, keep it swappable. |
| Tests | `pytest-django`, `factory_boy`, `coverage` | §60. |
| Lint/format | `ruff` + `black` | §64. |
| File type check | `python-magic` (`python-magic-bin` on Windows) | §35 "never trust client MIME". |
| DRF | **Not installed** until a real API consumer exists | §9, §88. |

### 4.2 Project layout

```
qistas/
  manage.py
  pyproject.toml
  .env.example
  .gitignore
  docker-compose.yml          # Postgres for dev parity
  qistas/                     # project package
    settings/{base,dev,prod,test}.py
    urls.py  wsgi.py  asgi.py
  apps/
    common/       # abstract models, mixins, permission core, UI tags, errors, pagination
    accounts/     # custom User, roles, auth views, RBAC framework
    audit/        # AuditLog + logging helper (minimal in P1)
    dashboard/    # dashboard views/selectors (placeholder in P1, real in P9)
    clients/      # P2
    cases/        # P3  (cases, parties, notes, timeline)
    courts/       # P3 stub / P4 full
    hearings/     # P4
    agenda/       # P4/P5  (calendar views — 'calendar' would shadow the stdlib module)
    tasks/        # P5  (tasks + deadlines)
    documents/    # P6
    contracts/    # P7
    finance/      # P8  (invoices, line items, payments, expenses, fee agreements)
    notifications/# P11
    reports/      # P10
  templates/
    base.html  components/  errors/  auth/  dashboard/
  static/ (src/, vendor/, fonts/, img/)
  docs/
    architecture.md
    adr/            # one file per significant decision
```

### 4.3 Per‑app internal structure

`models.py` · `selectors.py` (permission‑scoped read queries) · `services.py` (transactional writes + audit) · `forms.py` · `views.py` (thin) · `urls.py` · `permissions.py` (object‑level policy functions) · `admin.py` (superuser only) · `templates/<app>/` · `tests/`.

**Rule:** views never contain business logic or money math; they call `services`/`selectors`. Business rules (payment validation, overdue logic, totals) live server‑side in services (§38, §42, §90).

### 4.4 Cross‑cutting building blocks (Phase 1)

- `common.models.TimeStampedModel` — `created_at`, `updated_at`.
- `common.models.AuthoredModel` — `created_by`, `updated_by` (`on_delete=SET_NULL`).
- `common.models.SoftDeleteModel` + `SoftDeleteManager` — `deleted_at`, `all_objects` escape hatch; **partial unique indexes** so unique numbers ignore soft‑deleted rows.
- `common.reference_numbers` — transaction‑safe sequence generator.
- `common.permissions` — `capabilities.py` (role → capability map), `RoleRequiredMixin`, `ObjectScopedMixin` (uses `Model.objects.for_user(user)`), `policy` base.
- `common.middleware.LoginRequiredMiddleware` — everything requires auth except the auth pages and error pages.
- Current‑request access for audit/authored fields: **passed explicitly** from view → service (no thread‑locals).
- `common.templatetags` — `{% can %}`, badge, table, empty‑state, etc.
- Error views/templates for 400/403/404/500.

### 4.5 Settings posture

`USE_TZ=True`, `LANGUAGE_CODE='ar'`, `LANGUAGES=[('ar', 'العربية')]`, `LocaleMiddleware`, `gettext` wired. Secure‑cookie / CSRF / HSTS / security‑headers switched on in `prod.py`; `manage.py check --deploy` must be clean. Secrets only via env (§65).

### 4.6 Soft‑delete / retention matrix (draft — confirm per phase)

| Entity | Delete policy |
|---|---|
| AuditLog | **Append‑only.** No ORM/admin delete. `actor` `on_delete=SET_NULL`. |
| Case, Hearing, Invoice, Payment, Contract, Document | **No hard delete.** Soft‑delete (recoverable, audited) + status‑based archival. FKs `PROTECT`/`SET_NULL`, never `CASCADE`. |
| Client | No hard delete while it has cases/invoices (`PROTECT`); soft‑delete/`archived` otherwise. |
| Task, Note, Deadline, Meeting | Soft‑delete, audited. |
| User | Never deleted — `is_active=False`; offboarding reassigns open work. |
| Reference/lookup (CaseType, Court, categories) | `is_active=False` instead of delete. |

---

## 5. Domain model proposal (whole system — built incrementally, per phase)

> Phase 1 builds only `User`, roles, `AuditLog`, and the common abstractions. Everything below is the target ER map so early migrations don't paint us into a corner.

### 5.1 Accounts / core

- **User**(`AbstractBaseUser`, `PermissionsMixin`): `email` (unique, `USERNAME_FIELD`), `phone`, `first_name`, `last_name`, `role`, `is_active`, `is_staff`, `is_superuser`, `last_login`, `created_at`, `updated_at`. Custom `UserManager` (`create_user` / `create_superuser`).
- **Role** (`TextChoices`): `OFFICE_MANAGER`, `LAWYER`, `PARALEGAL`, `ADMIN_CLERK`, `FINANCE_CLERK`. Mirrored by seeded Django **Groups** (data migration + `sync_roles` management command re‑run each phase as new model perms appear).
- **ParalegalProfile** (or `User.supervisors` M2M, self‑referential) — links a paralegal to the lawyer(s) whose cases they support (decision #16).
- **AuditLog**: `actor` (SET_NULL), `action`, `entity_type`, `entity_id`, `object_repr`, `changes` (JSON `{field: [old, new]}`), `ip_address`, `user_agent`, `created_at`. Append‑only.

### 5.2 Clients (Phase 2)

- **Client**: `client_number` (unique, generated), `type` (`individual|company`), `full_name`, `company_name`, `national_id`, `registration_number`, `phone`, `secondary_phone`, `email`, `address`, `city`, `status` (`active|inactive|prospect|archived`), `notes`, timestamps + authored + soft‑delete.
  Constraints: `type='individual' ⇒ full_name` set; `type='company' ⇒ company_name` set (`CheckConstraint`); `pg_trgm` indexes on name/phone/number.

### 5.3 Cases (Phase 3)

- **Case**: `case_number` (unique), `internal_reference`, `title`, `type` (FK **CaseType**), `client` (FK `PROTECT`), `assigned_lawyer` (FK User `PROTECT`), `court` (FK `SET_NULL`), `department`, `status`, `stage`, `priority`, `filing_date`, `claim_amount` (Decimal), `description`, `legal_notes`, `internal_notes`, timestamps + authored + soft‑delete. `next_hearing` = cached derived value.
- **CaseType**: `name`, `is_active`, `order` — seeded with the §23 list; configurable later.
- **CaseLawyer** (through): `case`, `lawyer`, `role` (`lead|supporting`).
- **CaseParty**: `case`, `party_role` (`client|opponent|lawyer|representative|other`), `name`, contact fields, `linked_client` (FK null), `linked_user` (FK null), `notes` — relationship model, **not** a single "opposing party" field (§27).
- **Note**: `case` (FK null), `client` (FK null), `kind` (`general|legal|correspondence`), `body`, `visibility` (`internal|shared`), authored, timestamps, soft‑delete.
- **CaseEvent** (timeline): `case`, `event_type`, `summary`, `actor`, `occurred_at`, generic reference to the source row — append‑only, written by services (§26 timeline). Phase 3 lays the foundation; later phases emit events.

### 5.4 Courts (Phase 3 stub / Phase 4 full)

- **Court**: `name`, `type`, `city`, `department`, `address`, `phone`, `notes`, `is_active`. Reusable across cases (§28).

### 5.5 Hearings (Phase 4)

- **Hearing**: `case` (FK `PROTECT`), `court` (FK `SET_NULL`), `scheduled_at` (tz‑aware `DateTimeField`), `hearing_type`, `lawyer` (FK), `room`, `status` (`scheduled|held|postponed|cancelled`), `notes`, `result`, `next_action`, timestamps + authored + soft‑delete.
  Workflow (§30): marking a hearing `held`/`postponed` with a next date **creates the next Hearing**, appends a `CaseEvent`, refreshes `Case.next_hearing`, and (Phase 11) feeds notifications.

### 5.6 Tasks & deadlines (Phase 5)

- **Task**: `title`, `description`, `assigned_to` (FK), `case` (FK null), `client` (FK null), `priority`, `status` (`new|in_progress|done|cancelled`), `due_date`, `completed_at`, `created_by`, timestamps, soft‑delete. `is_overdue` = computed (`due_date < today AND status not in {done, cancelled}`), never stored (decision #6).
- **Deadline**: `case` (FK), `title`, `type` (`limitation|appeal|filing|other`), `due_at`, `critical` (bool), `met_at` (null), `notes` — cannot be "completed", only "met"; alarmed early and loudly.

### 5.7 Agenda / calendar (Phase 4–5)

- **Meeting**: `title`, `scheduled_at`, `participants` (M2M User), `case`/`client` (FK null), `location`, `notes`.
- No dedicated "calendar event" table — `agenda.selectors` unions Hearings + Task due dates + Deadlines + Contract `end_date` + Meetings, each row linking back to its source (§33).

### 5.8 Documents (Phase 6)

- **Document**: `name`, `document_type` (FK/choices), `file` (private storage), `original_filename`, `content_type` (detected), `size`, `checksum` (sha256), `description`, `uploaded_by`, `client`/`case`/`contract`/`invoice` (FK null), timestamps, soft‑delete.
  Constraint: at least one owner FK set (`CheckConstraint`). Download only through `documents:download` → policy check → `audit('document_downloaded')` → stream / `X‑Accel‑Redirect`.
- **DocumentVersion** (seam only, not built in P6): `document`, `version_no`, `file`, `uploaded_by`, `created_at` (§36).

### 5.9 Contracts (Phase 7)

- **Contract**: `contract_number` (unique), `client` (FK `PROTECT`), `case` (FK null), `contract_type` (FK/choices), `start_date`, `end_date`, `value` (Decimal), `status` (`draft|active|expired|cancelled`), `description`, `notes`, timestamps, soft‑delete. Expiry surfaced by a selector (`status=active AND end_date <= today + N days`).

### 5.10 Finance (Phase 8)

- **Invoice**: `invoice_number` (unique), `client` (FK `PROTECT`), `case` (FK null), `issue_date`, `due_date`, `discount` (Decimal), `tax_rate` (Decimal), `tax_amount` (Decimal, computed), `subtotal` (computed from items), `total` (computed), `paid_amount` (Decimal cache), `status` (`draft|unpaid|partial|paid|cancelled`), `notes`, timestamps, soft‑delete.
  Constraints: `CheckConstraint(paid_amount >= 0)`, `CheckConstraint(paid_amount <= total)`, `discount >= 0`.
- **InvoiceLineItem**: `invoice` (FK `CASCADE` within the aggregate), `description`, `quantity`, `unit_price`, `amount`.
- **Payment**: `invoice` (FK `PROTECT`), `amount` (Decimal, `> 0`), `received_on`, `method`, `reference`, `recorded_by`, `notes`, `created_at`. **Immutable**; corrections = reversing entry. `PaymentService` runs inside `transaction.atomic()` + `select_for_update()` on the invoice and rejects `amount > remaining` (§40).
- **Expense**: `description`, `amount` (Decimal), `category` (FK/choices), `incurred_on`, `scope` (`office|case|client`), `case`/`client` (FK null), `billable` (bool), `recorded_by`, `receipt` (FK Document null), `notes`.
- **FeeAgreement** (case fees, decision #18): `case` (FK), `fee_type` (`fixed|hourly|contingency|retainer`), `amount`/`hourly_rate`/`percentage`, `agreed_on`, `notes`. Invoices may reference it. **Needs product clarification.**

### 5.11 Notifications (Phase 11)

- **Notification**: `recipient` (FK), `type`, `title` (Arabic, action‑oriented — §99), `body`, `url`, generic reference to the source, `is_read`, `read_at`, `created_at`. Emitted by domain services + scheduled scanners (hearing/task/invoice/contract/deadline).
- **NotificationPreference** (optional): per‑type opt‑out, lead times.

### 5.12 Reports (Phase 10)

No models — permission‑scoped selectors + export utilities (CSV with UTF‑8 BOM, print stylesheet, optional PDF).

### 5.13 Global integrity rules

- Money: `DecimalField(max_digits=14, decimal_places=2)` everywhere; all arithmetic in services; DB `CheckConstraint`s; `transaction.atomic()` for multi‑row writes (§42).
- FKs on legal records: `PROTECT` or `SET_NULL`, **never** `CASCADE` across aggregates (§57).
- Unique reference numbers: **partial** unique indexes excluding soft‑deleted rows.
- Indexes only where query patterns justify (§58): `*_number`, `phone`, `scheduled_at`, `due_date`, `status`, `created_at`, plus `pg_trgm` for search.

---

## 6. RBAC & authorization strategy

Four enforced layers; the UI is never a security boundary (§15).

### Layer 1 — Authentication gate
Project‑wide `LoginRequiredMiddleware` (allowlist: auth pages, error pages, static). Secure session cookies, CSRF, `SESSION_COOKIE_AGE` idle timeout, `django-axes` lockout, optional TOTP MFA. Production hides auth errors and stack traces (§14, §53).

### Layer 2 — Role‑based feature access (coarse)
5 roles → seeded Groups holding model‑level permissions. A **capability map** (`capabilities.py`) resolves `can(user, "cases.view")`, used both to render the permission‑aware sidebar (§16 — cosmetic) and by `RoleRequiredMixin` on views (real check). Office manager ≈ all app capabilities (not necessarily Django `is_superuser`). Admin moves users between roles (audited as "Permission changed", §46). Capability sets are fixed in code for v1 (decision #12).

### Layer 3 — Object‑level authorization (fine)
Policy functions per entity in `<app>/permissions.py`, enforced **two ways, both mandatory**:

1. **Queryset scoping** — `Model.objects.for_user(user)` used in *every* list, detail, FK dropdown, autocomplete, and search. 
2. **Object fetch** — `get_object_or_404(Case.objects.for_user(request.user), pk=...)` so URL tampering yields **404** (not 403 — don't confirm the row exists).

Indicative case rules (pending decisions #15–17):

| Role | Cases | Financial data | Legal/internal notes |
|---|---|---|---|
| Office manager | all | all | yes |
| Lawyer | all office cases (read); edit only where lead/supporting | read‑only summary | yes |
| Paralegal | supervisors' cases + cases with an assigned task | none | no |
| Admin clerk | all (logistics view) | none | no |
| Finance clerk | all (finance view) | full | no |

Child records (hearings, tasks, documents, invoices, notes) inherit their parent case/client scope. Field‑level visibility (`legal_notes`, `internal_notes`, money figures) gated in selectors and templates, not just hidden with CSS.

### Layer 4 — Audit of authorization events
Login / logout / failed login / lockout, role/permission changes, document downloads, and (optionally) denied‑access attempts are written to `AuditLog`.

### Testing (§60)
A permission‑matrix test module: for every `(role × entity × action × ownership)` assert allow/deny, plus explicit URL‑tampering tests and a `assert_forbidden` / `assert_not_found` helper. Phase 1 ships the **framework + its tests**; entity policies arrive with their entities.

---

## 7. Implementation phases

The spec fixes the 14‑phase sequence (§82). It is coherent and I propose to **keep it as‑is**, with these clarifications folded in (no reordering):

- **Phase 1** additionally includes a **minimal `AuditLog` + logging seam** and the **async strategy decision** (cron + management commands), because Phases 5 and 11 depend on both.
- **Courts**: minimal `Court` model in Phase 3 (Case needs the FK); full Court management UI in Phase 4.
- **"Overdue"** implemented as a computed state, not a stored status (Phases 5 & 8) — divergence from the literal spec enum, flagged.
- **Invoice line items** built in Phase 8 (not deferred).
- **Deadlines** as their own model in Phase 5.

Each phase still ends: implement → test → code‑review → security‑review (where relevant) → fix → **Phase Completion Report** → **STOP** → wait for `APPROVE PHASE N` / `ابدأ المرحلة N`.

---

## 8. Phase 1 — Foundation: detailed plan

**Goal:** a secure, themed, RTL Django shell that a user can log into, with the authorization framework, audit seam, reusable UI kit, error pages, tests, and CI in place — and **zero domain entities**.

### 8.1 Deliverables

1. **Project scaffold** — `pyproject.toml` (pinned deps), `qistas/settings/{base,dev,prod,test}.py`, `.env.example`, root `.gitignore`, `manage.py`, `wsgi/asgi`, `docker-compose.yml` (Postgres 16), `README.md` (setup), CI workflow (`ruff`, `black --check`, `pytest`, `manage.py check --deploy`).
2. **`common` app** — `TimeStampedModel`, `AuthoredModel`, `SoftDeleteModel` + manager, `reference_numbers` util, permission core (`capabilities.py`, `RoleRequiredMixin`, `ObjectScopedMixin`, policy base), pagination helper, template tags, error views.
3. **`accounts` app** — custom `User` + `UserManager` (email login), `Role` choices, migration seeding Groups + `sync_roles` command, themed Arabic auth flows (login, logout, password change, password reset ×4) on Django built‑ins, `django-axes` config, idle‑timeout, `LoginRequiredMiddleware`, `django-otp` scaffold (not enforced — pending decision #31).
4. **`audit` app (minimal)** — `AuditLog` model, `record_audit(actor, action, obj, changes, request)` helper, auth signal receivers (login/logout/failed), admin registered read‑only with delete disabled.
5. **UI foundation** — Tailwind standalone build (`static/src/app.css` → `static/css/app.css`), design tokens (navy / slate / warm off‑white / neutral gray / bronze) as CSS vars + Tailwind theme, **self‑hosted IBM Plex Sans Arabic**, `templates/base.html` (RTL shell, right sidebar, topbar, toast region, vendored HTMX + Alpine), component partials for the §49 kit, data‑driven **permission‑aware navigation** (§16) with mobile collapse, themed **400/403/404/500** pages, a dev‑only component style‑guide page.
6. **Dashboard placeholder** — authenticated landing route with proper Arabic empty‑states (real dashboard = Phase 9); login redirects here.
7. **Project tracking** — `PROJECT_STATUS.md` (§78) + refreshed `.wolf/STATUS.md`.
8. **Testing foundation** — `pytest-django` config, `conftest.py`, `UserFactory`, `tests/utils.py` (`assert_login_required`, `assert_forbidden`, `assert_not_found`), and the Phase 1 test suite (below).
9. **Docs** — `docs/architecture.md` + `docs/adr/` capturing every decision in §3.

### 8.2 Database changes (Phase 1)

- `accounts.User` (custom `AUTH_USER_MODEL` — must be set before the first migration).
- Django `auth` Groups seeded for the 5 roles (data migration).
- `audit.AuditLog`.
- `django_axes` tables (migration).
- `django_otp` / TOTP tables (scaffold).

No business tables.

### 8.3 Tests (Phase 1)

- **Auth:** login success / wrong password / inactive user; logout; password‑change requires auth; password‑reset token flow; `axes` lockout after N failures; session‑cookie flags in prod settings; redirect chains.
- **Authorization framework:** `capabilities.can()` truth table per role; `RoleRequiredMixin` blocks/allows; `ObjectScopedMixin` + a dummy model prove `for_user` scoping and 404‑on‑tamper.
- **Navigation:** sidebar items hidden/shown by capability.
- **Errors:** 403/404/500 render themed templates with `DEBUG=False`.
- **Audit:** login / logout / failed‑login write `AuditLog`; `AuditLog` delete is blocked.
- **Smoke:** `manage.py check --deploy` clean on prod settings; migrations apply on a fresh DB.

### 8.4 Phase 1 Definition of Done

Migrations apply cleanly on empty Postgres · all Phase 1 tests green · `check --deploy` clean · login → placeholder dashboard → logout works · nav filters by capability · themed error pages with `DEBUG=False` · RTL verified visually (sidebar right, forms/tables/dropdowns mirrored) · `PROJECT_STATUS.md` present · code review + auth security review done · every §3 decision recorded as an ADR.

### 8.5 Explicitly out of Phase 1 (Deferred Items)

Any Client/Case/etc. model, the real dashboard, DRF, the notification scheduler *implementation* (decision recorded only), reports, global search implementation, PDF export, MFA enforcement.

---

## 9. Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **RTL depth** — spec explicitly warns against `direction: rtl` alone; every component, table, form, modal, calendar, icon must be mirrored. Rework risk if the kit isn't RTL‑native. | Build the component kit RTL‑first with logical properties; visual review checklist; dev style‑guide page; `/designqc` per phase. |
| 2 | **No async worker in the stack** vs time‑based reminders / overdue / email / PDF. | Decide now: cron + management commands, `django-q2` seam. |
| 3 | **Arabic RTL PDF** (Phase 10) — genuinely hard; WeasyPrint has heavy system deps. | Ship CSV + print stylesheet first; treat PDF as optional; spike WeasyPrint early in Phase 10. |
| 4 | **Reference‑number races & uniqueness** across concurrent creates. | Counter row + `select_for_update` inside the create transaction; partial unique index. |
| 5 | **Stored financial aggregates drift** from payments. | Cache updated only inside the Payment transaction; DB `CheckConstraint`; a periodic reconciliation command. |
| 6 | **Object‑level authz gaps** — one unscoped queryset leaks data. | Mandatory `for_user` manager pattern + `get_object_or_404(scoped_qs)`; permission‑matrix tests; review checklist item every phase. |
| 7 | **Multi‑tenancy retrofit** if SaaS is later wanted. | Confirm single‑tenant now; keep models tenancy‑ready (no cross‑office assumptions baked into logic). |
| 8 | **Arabic search quality** (Postgres FTS stemming is weak). | `pg_trgm` + `unaccent`; revisit if volume demands a real search engine. |
| 9 | **Audit completeness / tamper resistance / IP capture.** | Explicit request→service plumbing; append‑only `AuditLog`; DB‑level delete revocation in Phase 12. |
| 10 | **Soft‑delete vs unique constraints** interaction. | Partial unique indexes from the first migration that introduces each number. |
| 11 | **File‑upload security** — magic bytes, path traversal, prod storage. | Allowlist + `python-magic` + safe stored names + authorized download view; storage backend decided in Phase 6. |
| 12 | **Windows dev vs Linux prod parity.** | Postgres via Docker Compose; CI runs on Linux; avoid path/case assumptions. |
| 13 | **Model churn in early phases** breaking later migrations. | Keep the full ER map (§5) in view; additive migrations; `sync_roles` re‑run per phase. |
| 14 | **Dashboard N+1 / expensive aggregates** (Phase 9). | `select_related`/`prefetch_related`, selector layer, short‑TTL cache, query‑count tests. |
| 15 | **`auto_now` doesn't fire on `QuerySet.update()`** — silent `updated_at` staleness. | Services use `.save()`/model methods for audited writes; document the rule. |

---

## 10. Decisions I need from you

**Blocking Phase 1:**

1. Tenancy: **single‑tenant** (recommended) or multi‑tenant SaaS?
2. Target **jurisdiction / country** (IDs, courts, tax, Hijri)?
3. Language: Arabic‑only, or **ar/en bilingual** (I'll build gettext‑ready either way)?
4. Currency + tax: **single currency + single configurable VAT rate** (recommended)?
5. Async: **cron + management commands** (recommended) or `django-q2`/Celery?
6. "Overdue" as a **computed state**, not a stored status (recommended, diverges from spec enum)?
7. Include a **minimal AuditLog + logging seam in Phase 1** (recommended)?
8. Django admin = **superuser/developer only** (recommended)?
9. **CI** (GitHub Actions) in Phase 1 (recommended)?
10. RBAC: **fixed capability sets per role**, membership editable (recommended)?
11. Branch: keep `master` or rename to **`main`**? First commit adds `.gitignore` + `.env.example`.
12. MFA: **scaffold now, enforce in Phase 12** (recommended) or enforce now?
13. Test stack: **pytest‑django + factory_boy** (recommended)?
14. Dev DB via **Docker Compose Postgres** — OK on your machine? (Docker verified present.)

**Needed before their phase (not Phase 1):** decisions #15–34 in the table in §3.2 — most importantly lawyer case visibility (#15), paralegal scope (#16), field‑level note visibility (#17), "case fee" definition (#18), and invoice balance strategy (#20).

---

## 11. What happens next

I will **not** write any code until you approve. On your signal I will:

1. Answer/confirm the §10 decisions with you.
2. Produce the final Phase 1 implementation checklist (file‑by‑file).
3. Begin Phase 1 only after **`APPROVE PHASE 1`** / **`ابدأ المرحلة 1`**.

**STOP — waiting for your review and approval.**
