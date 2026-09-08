# Qistas — Adversarial Architecture & Security Review ("/grill-me")

> Reviewer stance: senior Django architect + application-security reviewer, deliberately hostile to the plan.
> Inputs reviewed: `QISTAS_PROJECT_SPEC.md`, repo state, and `QISTAS_PHASE_0_ANALYSIS.md` (the proposed architecture / domain model / RBAC / Phase 1 plan).
> Date: 2026-09-08. **No code, migrations, or models were created.**
> Note: the repo's `/grill-me` skill is not registered for this CLI; this review was performed manually to the same intent.

Severity legend: **CRITICAL** (stop-the-line, wrong foundation) · **HIGH** (expensive to fix later, fix now or very soon) · **MEDIUM** (real risk, schedule it) · **LOW** (minor) · **RECOMMENDATION** (improvement, not a defect).

---

## PART 1 — FINDINGS

### A. Django architecture & app boundaries

---

**A1 — Creating 16 apps up front for a 14-phase incremental build.** — MEDIUM
1. *Problem:* The Phase 0 plan scaffolds `apps/{clients,cases,courts,...}` — 13 of them empty until their phase. Empty apps are dead code (spec §64), add migration-graph noise, and invite premature cross-imports.
2. *Why it matters:* Churn and false structure; a reviewer can't tell what's real; import cycles get created "to be ready".
3. *Recommended solution:* Phase 1 creates **only** `core`, `accounts`, `audit`. Each later phase creates its own app. Keep a one-line app roadmap in `docs/architecture.md`.
4. *Fix before Phase 1?* **Yes** (it's a Phase 1 scoping decision).

---

**A2 — `common` app renamed from spec's `core/`, silently.** — LOW
1. *Problem:* Spec §11 lists `core/`. Phase 0 doc uses `common/` with no justification. §80 forbids silent structural changes.
2. *Why it matters:* Trivial technically, but it's exactly the kind of undocumented drift the spec's process rules exist to prevent.
3. *Recommended solution:* Use `core/` per spec. (The `calendar/` → `agenda/` rename **is** justified — stdlib name clash — and should be recorded as an ADR.)
4. *Fix before Phase 1?* **Yes.**

---

**A3 — Mandatory `services.py` + `selectors.py` in every app from day 1.** — RECOMMENDATION
1. *Problem:* Spec §10 says services "when business logic becomes complex" and selectors "where useful" — conditional, not universal. Phase 0 mandates the full HackSoft layering everywhere.
2. *Why it matters:* Over-engineering (spec §298, §300). A 3-field CRUD form does not need a service layer; the indirection slows every future contributor.
3. *Recommended solution:* Standardize exactly **one** cross-cutting pattern early: permission-scoped managers/querysets. Introduce a service function only for genuinely multi-step transactional flows (record payment, complete hearing, upload document, assign case). Fat models + forms for the rest.
4. *Fix before Phase 1?* No — but bake the *principle* into `docs/architecture.md` now so Phase 2 doesn't cargo-cult it.

---

**A4 — `dashboard` as an early app.** — LOW
1. *Problem:* A dashboard aggregates across every domain and cannot exist before those models. Phase 0 lists it as an app with a "placeholder" in Phase 1.
2. *Why it matters:* Minor coupling/ordering confusion.
3. *Recommended solution:* Phase 1's authenticated landing page is a plain view in `core`. The real `dashboard` app is created in Phase 9.
4. *Fix before Phase 1?* **Yes** (naming/scoping).

---

### B. Custom User & RBAC

---

**B1 — Single `role` CharField on User is the wrong RBAC primitive.** — HIGH
1. *Problem:* One enum = one role per person. Real offices: the office manager is also a practising lawyer; a senior lawyer also approves finance; a paralegal covers reception. Spec §12 describes roles but §12/§46 talk about *permissions* and audit "Permission changed" — implying editable, composable access.
2. *Why it matters:* Migrating from a `role` column to group-based auth **after users and object-policies exist** is a painful, error-prone change touching every permission check and every test.
3. *Recommended solution:* Make **Django Groups the source of truth** from Phase 1. Seed 5 groups matching the spec roles. `User.groups` (standard M2M) drives everything; the capability map is keyed by group. Keep `role` only as an optional derived display hint, or drop it (this is a documented deviation from spec §13 — see Decisions).
4. *Fix before Phase 1?* **Yes** — this is the RBAC foundation.

---

**B2 — Login identifier assumed to be email; spec never says so.** — HIGH
1. *Problem:* Phase 0 sets `USERNAME_FIELD = 'email'`, `unique=True`. Many MENA law offices onboard staff without individual work email. Email-as-identity also blocks the same person existing at two offices if SaaS ever happens, and makes phone-only password reset impossible.
2. *Why it matters:* `USERNAME_FIELD` is effectively immutable once users exist — changing it later is a data migration + auth-flow rewrite + retraining.
3. *Recommended solution:* Confirm the real identifier with the product owner. Safe default: a dedicated `username` / employee-code as `USERNAME_FIELD`; `email` nullable but unique-when-present (`UniqueConstraint(condition=~Q(email='')`); phone likewise. Self-service password reset only for users with a verified email; others get admin-issued temporary passwords.
4. *Fix before Phase 1?* **Yes.**

---

**B3 — `AbstractBaseUser` + `PermissionsMixin` from scratch vs subclassing `AbstractUser`.** — RECOMMENDATION
1. *Problem:* Full custom user is more surface area and a classic source of subtle bugs (superuser creation, `is_active` semantics, admin integration, `normalize_email`).
2. *Why it matters:* Time and risk across a 14-phase solo build; the spec wants "custom user" (§13), not "hand-rolled auth".
3. *Recommended solution:* Subclass `AbstractUser`, add `phone` and any needed fields, set the identifier field. Only drop to `AbstractBaseUser` if the identifier decision (B2) truly requires removing `username`.
4. *Fix before Phase 1?* **Yes** (it's the User model).

---

**B4 — Assigning permissions to groups inside data migrations, "re-run each phase".** — HIGH
1. *Problem:* Phase 0 proposes a data migration to seed groups + permissions, plus a `sync_roles` command "re-run each phase". Migrations run once; permission codenames don't exist until their app is migrated; ordering across many apps is fragile; a changed data migration doesn't re-apply.
2. *Why it matters:* Broken/ँinconsistent permission state between environments; "works on my machine" auth bugs.
3. *Recommended solution:* Migrations create **only** the `Group` rows (or nothing). One **idempotent** `sync_roles` management command is the single source of truth for group→permission mapping; it runs in CI (assert no drift) and on every deploy. A `post_migrate` hook may call it in dev.
4. *Fix before Phase 1?* **Yes.**

---

**B5 — No `Person`/`Party` concept distinct from `User`.** — MEDIUM (Phase 3, note now)
1. *Problem:* Lawyers appear as system users, case parties, hearing attendees, task assignees. Opposing counsel and client representatives are parties but not users. `Case.assigned_lawyer` FK→User means a lawyer must remain an active user to hold a case; `PROTECT` then blocks off-boarding.
2. *Why it matters:* Off-boarding a departed lawyer becomes a data-surgery task; conflict-of-interest data (opposing counsel history) has nowhere to live.
3. *Recommended solution:* Phase 3: `CaseParty` with free-text identity + optional `linked_user`/`linked_client`; an office-wide `Party` directory for repeat opponents/counsel. Off-boarding = reassignment workflow, `assigned_lawyer` `on_delete=PROTECT` but deactivation allowed.
4. *Fix before Phase 1?* No — but don't model `assigned_lawyer` in a way that assumes permanence.

---

### C. Object-level authorization & queryset scoping

---

**C1 — `for_user()` as (or near) the default manager is a footgun.** — HIGH
1. *Problem:* If scoping is the default behavior, shell/admin/imports/cron get silently filtered; if it's opt-in, `.objects.all()` silently bypasses it. "Two ways, both mandatory" is convention, not enforcement.
2. *Why it matters:* A single unscoped queryset in one view = a confidentiality breach in a legal system. Conventions are violated under deadline pressure.
3. *Recommended solution:* (a) `for_user(user)` is an **explicit** queryset method, never the default. (b) A `ScopedQuerySet` base that tracks whether `for_user` was applied; a `ScopedObjectMixin`/`ScopedListMixin` for views that *requires* it and raises otherwise. (c) A DEBUG-only assertion + a test that every model list/detail view routes through a scoped queryset. (d) System code (cron, imports) uses `.objects` deliberately and is reviewed.
4. *Fix before Phase 1?* **Yes** — Phase 1 ships this framework and its tests.

---

**C2 — 404-on-forbidden as the blanket rule.** — MEDIUM
1. *Problem:* Phase 0 returns 404 for object-level denial "to avoid confirming existence". For an internal tool where all staff know cases exist, this produces "the link is broken" support tickets and hides real bugs.
2. *Why it matters:* Poor operability; wrong signal to users and to logs.
3. *Recommended solution:* **403 with a clear Arabic message** as the default for cross-role denial inside one office. Reserve 404 for cases where enumeration is a genuine threat — which only applies if lawyers are *strictly* siloed (see C3 / spec contradiction). Decide together.
4. *Fix before Phase 1?* Decide the policy before Phase 1; it's trivial to implement in Phase 3.

---

**C3 — Object-policy granularity is undefined and the spec contradicts itself.** — HIGH
1. *Problem:* §15 demands strict per-object siloing ("/cases/15 ok ⇒ /cases/16 must fail by URL"). §17/§43 dashboards and reports show "cases by lawyer", "all cases by status" — office-wide visibility. Are aggregates manager-only? Do lawyers see office-wide case *lists* but not *details* of non-assigned cases? Undefined.
2. *Why it matters:* This single decision shapes every queryset scoper, every report, the dashboard, and the 403/404 choice. Getting it wrong means re-scoping the whole app.
3. *Recommended solution:* Define a per-role visibility matrix now (list / detail / confidential fields / financial fields / aggregates), per entity. Recommended baseline: all staff see all office cases in **lists and aggregates**; **edit** and **confidential/financial fields** are role- and assignment-gated; strict siloing only if the office explicitly wants it.
4. *Fix before Phase 1?* **Decision yes**, implementation in Phase 3.

---

**C4 — Field-level confidentiality via template/selector gating will leak.** — HIGH
1. *Problem:* `legal_notes` / `internal_notes` hidden "in templates and selectors" must then also be stripped from: CSV exports, HTMX partials, `__str__`, audit `object_repr`, audit diffs, search snippets, print views, error pages, DRF (if ever). Every new surface is a new leak.
2. *Why it matters:* Privileged legal content disclosed to admin/finance staff is a professional-liability and privacy failure.
3. *Recommended solution:* Put the most sensitive fields on a **separate 1:1 model** (`CaseConfidential`) so access requires an explicit, policy-controlled join — a field you never selected can't leak. Plus a single `case.for_display(user)` projection used everywhere, and a test asserting the raw value never appears in rendered output for an unauthorized role.
4. *Fix before Phase 1?* No (Phase 3) — but choose "separate model vs flags" now; reversing it later is a data migration.

---

**C5 — Permission-respecting global search has no workable design.** — MEDIUM (Phase 2+)
1. *Problem:* Search across 5 entity types, each permission-filtered per row, with ranking and pagination, is either N queries or an un-permission-filterable SQL UNION. Arabic `pg_trgm` ranking across filtered sets is weak anyway.
2. *Why it matters:* Either slow, or a leak, or both.
3. *Recommended solution:* v1 = separate per-entity scoped queries, small `LIMIT` per type, grouped results, no cross-entity relevance ranking. Revisit only if users demand it.
4. *Fix before Phase 1?* No.

---

### D. Security & sensitive legal data

---

**D1 — No data-at-rest protection decision for the crown jewels.** — HIGH
1. *Problem:* `national_id`, `internal_notes`/`legal_notes`, and document *contents* have no encryption/storage-isolation plan. Spec §92/§35 demand protection; some jurisdictions mandate it.
2. *Why it matters:* Field encryption and encrypted document storage are **migration + key-management projects** once real data exists. Deciding after Phase 2 (first real client PII) is late.
3. *Recommended solution:* Decide now: (a) DB volume / managed-PG encryption (baseline, cheap); (b) application-level field encryption for `national_id` and similar (`pgcrypto` or `django-cryptography`) — yes/no; (c) documents on an encrypted volume or SSE-S3. Record as ADR. If field encryption is "yes", the `accounts`/`clients` models must accommodate it from their first migration.
4. *Fix before Phase 1?* **Decision yes** (before Phase 2 at the latest). Phase 1 sets DB-level encryption expectations in the deploy docs.

---

**D2 — `django-axes` locking by username+IP will lock out the whole office.** — HIGH
1. *Problem:* A law office behind one public IP / NAT: one person mistyping their password 5× can lock every account from that IP (or lock the IP).
2. *Why it matters:* Self-inflicted denial of service; the spec wants lockout (§14) but this configuration backfires.
3. *Recommended solution:* Lock by **username only** (`AXES_LOCKOUT_PARAMETERS = ["username"]`), sane threshold (e.g. 5–10), cool-off (e.g. 30 min), friendly Arabic lockout page, admin unlock action, and audit the lockout event.
4. *Fix before Phase 1?* **Yes** (Phase 1 implements auth hardening).

---

**D3 — Attorney–client conflict-of-interest / privilege is absent from spec and plan.** — MEDIUM / RECOMMENDATION
1. *Problem:* Nothing prevents assigning a lawyer to both sides of a matter, or surfacing a client to staff with a personal conflict. No privilege model.
2. *Why it matters:* Professional-conduct and liability exposure; hard to bolt on if the party model doesn't support it.
3. *Recommended solution:* Explicit scope decision with the product owner. Minimum: ensure `CaseParty` records opposing parties/counsel in structured form so a future conflict check is a query, not a schema change. Full conflict-checking is a candidate feature, likely out of v1.
4. *Fix before Phase 1?* No — but the party model (Phase 3) must not preclude it.

---

**D4 — HTMX + CSRF wiring is a common self-inflicted hole.** — LOW
1. *Problem:* If the CSRF token isn't wired for HTMX requests globally, POSTs 403 and someone "fixes" it by weakening CSRF.
2. *Why it matters:* CSRF is explicitly required (§14/§54).
3. *Recommended solution:* Phase 1 `base.html` sets `hx-headers='{"X-CSRFToken": "…"}'` (or `django-htmx` + `hx-headers` on `<body>`), documented; a test posts via the HTMX path.
4. *Fix before Phase 1?* **Yes** (it's in the base layout).

---

**D5 — Download hardening details unspecified.** — MEDIUM (Phase 6, note now)
1. *Problem:* No decision on `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, serving user files from a different origin, or blocking inline render of uploaded HTML/SVG (stored XSS).
2. *Why it matters:* An uploaded `.svg`/`.html` served inline from the app origin = script execution with a logged-in legal user's session.
3. *Recommended solution:* Always `attachment`; `nosniff`; ideally a separate media host/subdomain; re-encode images; extension + magic-byte allowlist excludes `svg`/`html`/`htm`. Design in Phase 6; note in the security ADR now.
4. *Fix before Phase 1?* No.

---

### E. Audit logging

---

**E1 — Half-adopting an audit library: "signals but no thread-locals".** — HIGH
1. *Problem:* Phase 0 wants automatic model-change capture (`old_values`/`new_values`, §46) **and** "no thread-locals, pass request explicitly". `django-auditlog` needs its thread-local actor middleware; you can't get automatic capture with actor/IP without it.
2. *Why it matters:* A muddled audit layer either misses the actor/IP or misses changes — and audit is a first-class requirement.
3. *Recommended solution:* Pick one. **Recommended:** `django-auditlog` **with** its actor middleware (thread-local for actor identity only — well-tested, standard), registered per model as each phase adds models; **plus** explicit `log_event(request, action, obj, …)` calls for non-ORM events (login, logout, failed login, lockout, document download, permission change, report export).
4. *Fix before Phase 1?* **Yes** — the mechanism choice sets the pattern for all 14 phases.

---

**E2 — The audit table becomes the largest unprotected PII store in the system.** — HIGH
1. *Problem:* Value diffs will contain `internal_notes` text, `national_id`, financial figures. §46 lets admins read audit logs — so admin/support can read privileged legal content via the audit trail even if the UI hides it.
2. *Why it matters:* Defeats the field-level confidentiality effort (C4); regulatory exposure.
3. *Recommended solution:* (a) **Allowlist** which fields are value-diffed; sensitive fields log "changed" with no old/new values. (b) Audit-detail views enforce the **same** object/field permissions as the underlying record. (c) "User viewed audit log" is itself an audited event. (d) `object_repr` must not embed sensitive text.
4. *Fix before Phase 1?* **Yes** — the `AuditLog` model + diff policy are built in Phase 1.

---

**E3 — "Audit records protected from deletion" (§46/§93) not achievable at the ORM layer.** — MEDIUM (Phase 12, design now)
1. *Problem:* ORM, admin, and migrations can always delete rows. True protection is DB-level.
2. *Why it matters:* A malicious or careless admin/deploy can erase the trail.
3. *Recommended solution:* Phase 1: no admin delete, no cascade into `AuditLog`, `actor` `on_delete=SET_NULL`. Phase 12: a `BEFORE DELETE/UPDATE` trigger that raises, or a DB role without DELETE, plus monthly partitioning (`pg_partman`) for volume. Note the plan now so the model design doesn't fight it.
4. *Fix before Phase 1?* Design yes, DB trigger in Phase 12.

---

**E4 — Synchronous audit writes + volume.** — LOW
1. *Problem:* Every mutation writes an audit row (with JSON diff) in the request path; unpartitioned growth.
2. *Why it matters:* Latency and table bloat at scale — modest at single-office scale.
3. *Recommended solution:* Keep audit writes **in the same transaction** as the change (consistency beats latency here). Index `created_at`, `(entity_type, entity_id)`, `actor`. Plan partitioning for Phase 12/14.
4. *Fix before Phase 1?* No.

---

### F. Financial integrity

---

**F1 — `paid_amount` cache constrained against a *computed* `total` that can change after payment.** — HIGH
1. *Problem:* `total` derives from line items. Editing a line item after payments exist either trips `CheckConstraint(paid_amount <= total)` or silently desynchronizes. The spec never states invoice immutability.
2. *Why it matters:* Core legal-accounting correctness; auditors and clients rely on issued-invoice stability.
3. *Recommended solution:* Once an invoice is **issued** (leaves `draft`), line items and monetary fields are **immutable**; corrections are credit notes / new invoices. Enforce in the service and, ideally, a trigger. Confirm this accounting rule with the product owner.
4. *Fix before Phase 1?* No (Phase 8) — but confirm the rule before Phase 8 design.

---

**F2 — No rounding policy.** — MEDIUM (Phase 8)
1. *Problem:* `sum(line amounts) − discount + tax` with per-line values: round-each-line vs round-the-sum give different totals. Spec §42 says Decimal, not *how* to round.
2. *Why it matters:* Off-by-a-cent invoices fail reconciliation and erode trust.
3. *Recommended solution:* ADR: `ROUND_HALF_UP`, 2 dp, round only final tax and grand total, line amounts stored at full precision or 2dp by rule; explicit tests with adversarial values.
4. *Fix before Phase 1?* No.

---

**F3 — No `currency` field on money models.** — LOW (cheap now, annoying later)
1. *Problem:* Even single-currency systems should stamp currency on Invoice/Payment/Expense for legal clarity and future multi-currency.
2. *Why it matters:* Retrofitting currency onto historical financial rows is unpleasant and ambiguous.
3. *Recommended solution:* `currency` CharField (ISO 4217), default from settings, on all financial models from Phase 8.
4. *Fix before Phase 1?* No.

---

**F4 — Payment corrections/voids undefined.** — MEDIUM (Phase 8)
1. *Problem:* "Payments immutable, corrections = reversing entry" but the spec (§40) defines no reversal and users *will* mis-key payments.
2. *Why it matters:* Without a flow, corrections become direct DB edits — unaudited, unsafe.
3. *Recommended solution:* Model `PaymentReversal` / `Payment.reversed_by` from the start; decide same-day void vs always-reverse; every path audited and transactional.
4. *Fix before Phase 1?* No.

---

**F5 — No optimistic locking on financial edit forms.** — MEDIUM (Phase 8)
1. *Problem:* `select_for_update` protects the payment transaction, not two users editing the invoice form; a stale form can overwrite `status`/fields.
2. *Why it matters:* Lost updates on financial records.
3. *Recommended solution:* Version/`updated_at` token on Invoice edit forms (`django-concurrency` or a hidden `updated_at` check); reject stale submits with an Arabic "record changed" message.
4. *Fix before Phase 1?* No — but consider the same pattern for Case edits (Phase 3).

---

### G. PostgreSQL & database constraints

---

**G1 — Universal soft-delete collides with `PROTECT` FKs, unique constraints, and "show all history".** — HIGH
1. *Problem:* (a) `PROTECT` checks row existence, not `deleted_at` — a "soft-deletable" Client with cases still can't be soft-deleted meaningfully. (b) Partial unique index `WHERE deleted_at IS NULL` lets a soft-deleted `case_number` be reused → user confusion and audit ambiguity. (c) Soft-deleted rows must still appear in timelines/audit but vanish from pickers — two query modes everywhere.
2. *Why it matters:* Pervasive, subtle query bugs and data-integrity ambiguity across the whole codebase.
3. *Recommended solution:* ADR before any model: soft-delete applies to a **small named set** (e.g. `Task`, `Note`, `Document`, maybe `Contract`); "archive" for `Case`/`Client` is a **status**, not deletion; reference numbers use **full** unique indexes (never reused, soft-deleted rows keep their number); true deletion is a rare admin action with mandatory reassignment; managers expose `active` (default) and `all_with_deleted`.
4. *Fix before Phase 1?* **Yes** — write the ADR; `core` base models depend on it.

---

**G2 — "Never CASCADE" is too absolute.** — MEDIUM
1. *Problem:* `InvoiceLineItem→Invoice`, `CaseParty→Case`, `CaseLawyer→Case` are true aggregate parts and *should* cascade; `Notification→source` should `CASCADE`/`SET_NULL`. Blanket "never cascade" is wrong.
2. *Why it matters:* Either orphan rows or an inability to ever clean up.
3. *Recommended solution:* Explicit per-FK `on_delete` table in the ADR: `CASCADE` **within** an aggregate root; `PROTECT`/`SET_NULL` **across** roots and for anything legally significant.
4. *Fix before Phase 1?* Decision yes; per-model application later.

---

**G3 — `CheckConstraint` for "individual ⇒ full_name" is harder than it looks.** — MEDIUM (Phase 2)
1. *Problem:* Django convention: no `null` on CharField → empty string, not NULL. A naive `full_name__isnull=False` check passes for `''`.
2. *Why it matters:* Constraint that doesn't actually constrain.
3. *Recommended solution:* `CheckConstraint(check=(Q(type='individual') & ~Q(full_name='')) | (Q(type='company') & ~Q(company_name='')))`, mirrored in `Model.clean()`, tested both layers.
4. *Fix before Phase 1?* No.

---

**G4 — Postgres extensions, version, and collation are unpinned.** — MEDIUM
1. *Problem:* `pg_trgm`, `unaccent`, and Arabic-aware sorting depend on PG version + ICU collation; the plan doesn't pin them.
2. *Why it matters:* "Sorts fine on my machine, wrong in prod"; missing extension = migration failure.
3. *Recommended solution:* Pin **PostgreSQL 16** in Docker; enable `pg_trgm` + `unaccent` via `CreateExtension` migrations in Phase 1; use an ICU collation for Arabic text columns where sorting matters (decide the locale with jurisdiction).
4. *Fix before Phase 1?* **Yes** (compose + first migration).

---

**G5 — Migration discipline across 14 phases of model churn.** — MEDIUM
1. *Problem:* Phases 2–8 heavily edit early models; `makemigrations` sprawl; a Phase 3 Case change can break Phase 2 tests.
2. *Why it matters:* Slow, fragile migration graph; missing-migration bugs.
3. *Recommended solution:* CI runs `makemigrations --check --dry-run`; migration review is a per-phase checklist item; plan a squash around Phase 8.
4. *Fix before Phase 1?* CI check yes; squash later.

---

### H. Reference number generation & race conditions

---

**H1 — Single global counter row + year-scoped formats + rollback gaps.** — HIGH
1. *Problem:* (a) One counter row serializes all case creation (acceptable at office scale, but be intentional). (b) Year-in-format (`C-2026-0001`) needs a **per-scope-per-year** counter; the first insert of a new year races. (c) A transaction that takes a number then rolls back leaves a **gap** — for `invoice_number`, auditors may require gap-free sequences.
2. *Why it matters:* Legal/audit implications; numbers are visible, permanent, and referenced externally. Very expensive to change after data is numbered.
3. *Recommended solution:* ADR before Phase 2:
   - `NumberSequence(scope, period, last_value)` table; `select_for_update`; increment in the **same transaction** as the insert.
   - Accept gaps for `case_number` / `client_number`; document it.
   - `invoice_number` assigned **only at issue** (not on draft); if strictly gap-free is required, add a compensating "voided number" record on failure. Confirm the requirement with the product owner.
   - Do **not** use a bare Postgres `SEQUENCE` (always gaps, awkward per-year reset).
   - Required: a real concurrency test (threads / `TransactionTestCase`).
2. *Fix before Phase 1?* **ADR yes**; implementation Phase 2.

---

### I. Document / file security

---

**I1 — "Private storage" is not the Django default and is easy to get wrong.** — HIGH (Phase 6, decide now)
1. *Problem:* `FileSystemStorage`/`MEDIA_ROOT` is typically web-served. "Private" needs storage outside the served path + an authorizing view, or private S3 + short-lived signed URLs. `FileField.url` will be called by accident somewhere.
2. *Why it matters:* Predictable/guessable document URLs = confidential legal files exposed (spec §35 explicitly forbids this).
3. *Recommended solution:* Custom storage under a non-served path; `upload_to` = UUID path, never the user filename; a storage subclass whose `.url()` **raises**; downloads only via `documents:download` (policy check → audit → `FileResponse`); `MEDIA_URL` unrouted. Decide local-vs-S3 now (affects the storage class and deploy).
4. *Fix before Phase 1?* Decision yes; implementation Phase 6.

---

**I2 — `python-magic` / `python-magic-bin` is a dev/prod parity trap on Windows.** — MEDIUM
1. *Problem:* `python-magic` needs libmagic; `python-magic-bin` (Windows) is unmaintained. If dev is native-Windows and prod is Linux, validation behaves differently.
2. *Why it matters:* "Validated fine locally, rejected/accepted differently in prod."
3. *Recommended solution:* Run the app in Docker (Linux) in dev too (see K1); then plain `libmagic` works everywhere. Combine with an extension allowlist + size limit + (for images) re-encode.
4. *Fix before Phase 1?* Tied to K1 (dev-in-Docker) — **yes** decide now.

---

**I3 — Multi-parent documents have ambiguous permission semantics.** — MEDIUM (Phase 6)
1. *Problem:* A `Document` with FKs to case + client + contract + invoice: can a user see it if they can see **any** parent, or **all** parents?
2. *Why it matters:* "Any" can leak a privileged case document via an invoice the finance clerk can see.
3. *Recommended solution:* Rule: visible iff the user can see the **primary** parent (define a single `owner` discriminator + optional secondary links), or the **most restrictive** parent. Decide and test.
4. *Fix before Phase 1?* No.

---

### J. RTL / i18n architecture

---

**J1 — "gettext-ready but ship Arabic only" is an unstable compromise.** — MEDIUM (needs a decision)
1. *Problem:* If Arabic is the only language forever, wrapping every string in `_()` and maintaining `.po` files is exactly the wasted effort the spec warns against (§63, §298). If English is ever coming, retrofitting `_()` across 14 phases is miserable.
2. *Why it matters:* Either ongoing overhead with zero payoff, or a large painful retrofit.
3. *Recommended solution:* Get a firm yes/no on ever supporting English (or any second language). Default if unknown: **commit to `gettext` now** (lowest regret) and be disciplined — it also forces clean separation of copy from logic.
4. *Fix before Phase 1?* **Yes** — it changes how every template and model is written from line 1.

---

**J2 — RTL plugin vs logical properties.** — MEDIUM
1. *Problem:* `tailwindcss-rtl` is largely unmaintained; mixing it with logical utilities causes inconsistency.
2. *Why it matters:* Getting the RTL foundation wrong means editing every template later (spec §204: "do not simply apply direction: rtl").
3. *Recommended solution:* Tailwind **v3.4+ native logical utilities** (`ps-*`, `pe-*`, `ms-*`, `me-*`, `text-start/end`, `start-0`) + `dir="rtl"` on `<html>`. No RTL plugin. Bake this into the component kit.
4. *Fix before Phase 1?* **Yes.**

---

**J3 — Bidi / mixed-direction content not addressed.** — HIGH
1. *Problem:* Arabic UI with Latin case numbers, phones, emails, money (`1,234.50`), and dates renders scrambled without `bdi` / `dir="auto"` / `unicode-bidi: isolate`.
2. *Why it matters:* The spec explicitly rejects superficial RTL; mangled numbers in a legal/financial UI are unacceptable and pervasive.
3. *Recommended solution:* Phase 1 component kit wraps all numbers/identifiers/money/dates in `<bdi>` (or a `{% num %}` tag); a visual QA checklist; test with realistic mixed data.
4. *Fix before Phase 1?* **Yes** (component kit).

---

**J4 — Numeral system (Arabic-Indic vs Western) and Hijri dates undecided.** — MEDIUM
1. *Problem:* Django's `ar` locale formatting can emit Arabic-Indic digits; MENA business/legal norms vary by country; some jurisdictions expect Hijri dates alongside Gregorian.
2. *Why it matters:* Wrong digits/calendar = re-touching every number and date display; Hijri is a cross-cutting integration.
3. *Recommended solution:* Decide explicitly (recommended: **Western digits** for money/IDs; Gregorian primary). Set Django `FORMAT_MODULE_PATH` explicitly rather than inheriting locale defaults. Hijri support is a jurisdiction-driven decision (ties to Decision D2).
4. *Fix before Phase 1?* Digit/format decision **yes**; Hijri can be deferred but must be known.

---

### K. Docker / development vs production parity

---

**K1 — "Postgres in Docker, Django native on Windows" is the parity gap that bites at deploy.** — HIGH
1. *Problem:* `libmagic`, `WeasyPrint` (Cairo/Pango — effectively unavailable on Windows), file-path case sensitivity, `X-Accel`, PG client encoding/collation, line endings, `cron` — all differ between a Windows host and a Linux prod box.
2. *Why it matters:* Bugs are discovered at deployment (Phase 14) instead of in Phase 1–13; PDF (Phase 10) may be undevelopable locally.
3. *Recommended solution:* Dockerize the **app** too: `compose` services `web` + `db` (+ `qcluster` if async chosen, + `nginx` later), code bind-mounted, developer works via `docker compose exec`. Windows is the editor host only. CI then mirrors dev exactly.
4. *Fix before Phase 1?* **Yes.**

---

**K2 — Tests must run on Postgres, not SQLite.** — MEDIUM
1. *Problem:* The spec relies on PG-specific features (`CheckConstraint`, partial indexes, `pg_trgm`, JSON operators, extensions). SQLite test runs would silently skip/behave differently.
2. *Why it matters:* Green tests that don't reflect production behavior.
3. *Recommended solution:* `settings/test.py` targets Postgres; CI uses a PG 16 service container; document that `manage.py test` needs the DB up.
4. *Fix before Phase 1?* **Yes.**

---

**K3 — Media/static persistence in containers.** — MEDIUM (note now)
1. *Problem:* Without a mounted volume, Phase 6 documents get written into an ephemeral container layer and vanish on rebuild.
2. *Why it matters:* Data loss in dev; wrong mental model for prod.
3. *Recommended solution:* Phase 1 compose declares a named `media` volume (even though uploads arrive in Phase 6); prod uses S3 or a persistent volume — decide with I1.
4. *Fix before Phase 1?* Compose volume yes; backend decision with Phase 6.

---

### L. Authentication security & MFA

---

**L1 — MFA "scaffold now, enforce Phase 12" leaves 11 phases without it.** — MEDIUM (decision)
1. *Problem:* Legal-data systems are high-value targets; deferring MFA enforcement to the last-but-two phase means all interim access (including demos with real-ish data) is single-factor.
2. *Why it matters:* Risk window; also, enforcing MFA late can disrupt established users.
3. *Recommended solution:* Phase 1: install `django-otp` + TOTP, wire the enforcement middleware **behind a setting** (`REQUIRE_MFA`), ship enrollment UI, allow per-user opt-in immediately, default-enforce for the `office_manager` group. Full rollout/enforcement decision at Phase 12. Confirm timing with the owner.
4. *Fix before Phase 1?* Install + setting-gated middleware **yes**; enforcement default is a decision.

---

**L2 — Session/idle-timeout and "remember me" semantics undefined.** — LOW
1. *Problem:* Confidential system → short idle timeout expected; but too short annoys lawyers in court.
2. *Why it matters:* Security/usability balance; needs to be a setting, tested.
3. *Recommended solution:* `SESSION_COOKIE_AGE` + a sliding idle-timeout middleware, both env-configurable; `SESSION_EXPIRE_AT_BROWSER_CLOSE` default true; no "remember me" for v1. Test the timeout.
4. *Fix before Phase 1?* **Yes** (auth foundation), values can be tuned later.

---

**L3 — Password reset flow depends on email that may not exist (see B2).** — MEDIUM
1. *Problem:* Self-service email reset is useless for phone-only/no-email users.
2. *Why it matters:* Lockouts with no recovery path → admin does DB surgery.
3. *Recommended solution:* Implement Django's email reset **and** an admin "issue temporary password (force change on next login)" action. Console email backend in dev; real provider deferred to Phase 14 (confirm acceptable).
4. *Fix before Phase 1?* **Yes** — both paths are auth foundation.

---

### M. Testing strategy

---

**M1 — The spec's mandated test surface (§60) is very large for a solo 14-phase build; "tests pass" in the DoD is undefined.** — MEDIUM
1. *Problem:* §60 mandates concurrency, permission, URL-manipulation, finance-edge, file-auth tests everywhere. Without tiering, "tests pass" is unmeasurable and the temptation is to skip silently.
2. *Why it matters:* Either the schedule slips badly or coverage is quietly abandoned — both violate the spec's process.
3. *Recommended solution:* Define a **tiered test policy** in `docs/architecture.md`:
   - **Tier 1 (must, blocks phase):** authentication, authorization (role + object + URL-tamper), money math & payment rules, reference-number concurrency, document access control, audit-write assertions.
   - **Tier 2 (should):** CRUD happy/validation paths, filters, search scoping.
   - **Tier 3 (nice):** UI states, pagination edge cases.
   - Soft coverage gate (report, don't fail) + hard gate on Tier 1 modules.
4. *Fix before Phase 1?* **Yes** — write the policy; Phase 1 builds the Tier-1 harness (`assert_login_required`, `assert_forbidden`, `assert_not_found`, `assertNumQueries` helpers, a concurrency test helper).

---

**M2 — No `assertNumQueries` / query-count regression strategy.** — MEDIUM (note now)
1. *Problem:* N+1s (case workspace §26, client profile §21, dashboard §9) will creep in without guardrails.
2. *Why it matters:* Performance degrades invisibly until real data exposes it (spec §59).
3. *Recommended solution:* `django-debug-toolbar` in dev; `assertNumQueries` on the heavy list/detail pages as they're built; a CI perf-smoke later.
4. *Fix before Phase 1?* Helper yes; per-page assertions as pages are built.

---

**M3 — `factory_boy` + faker locale for Arabic demo data (§61).** — LOW
1. *Problem:* Spec bans "John Doe / Lorem Ipsum"; factories default to English faker.
2. *Why it matters:* Demo data must feel real (§61).
3. *Recommended solution:* `faker` with `ar_AA`/`ar_SA` locale in factories + a curated list of realistic office/court/company names; demo-data command in a later phase.
4. *Fix before Phase 1?* No (factories yes, Arabic locale set when demo data matters).

---

### N. CI

---

**N1 — Proposed CI is too thin for a security-first spec.** — MEDIUM
1. *Problem:* "ruff + black + pytest + check --deploy" omits a PG service, `makemigrations --check`, dependency vulnerability scanning, and secret scanning — all directly implied by §54/§65.
2. *Why it matters:* Vulnerable deps and committed secrets are exactly the failure modes the spec calls out.
3. *Recommended solution:* GitHub Actions: PG 16 service container; `ruff` + `ruff format --check`; `pytest` (+ coverage artifact); `python manage.py makemigrations --check --dry-run`; `python manage.py check --deploy` against prod settings; `pip-audit`; `gitleaks`/`detect-secrets`. Add `.pre-commit-config.yaml` (same checks) for local speed.
4. *Fix before Phase 1?* **Yes** (Phase 1 deliverable).

---

**N2 — Branch/PR flow undefined; solo dev on `master`, no commits, spec expects code review per phase.** — LOW
1. *Problem:* The spec's phase gate + `/code-review` workflow implies PRs, but there's no branching model.
2. *Why it matters:* No natural home for the CI gate / review step; `master` vs `main` mismatch with the harness.
3. *Recommended solution:* Rename `master`→`main`; work on `phase/N-foundation` branches; PR into `main`; CI + `/code-review` gate the merge; tag `phaseN-approved` after user approval.
4. *Fix before Phase 1?* **Yes** (cheap, sets the rhythm).

---

### O. Performance risks

---

**O1 — Per-user permission-filtered dashboard is the top performance risk.** — MEDIUM (Phase 9, architect now)
1. *Problem:* 7+ KPIs + 5 sections, each an aggregate across cases/hearings/tasks/invoices, **filtered per user** → not globally cacheable, recomputed per page load.
2. *Why it matters:* The dashboard is the landing page; slowness here defines the product's feel (spec §59, §17).
3. *Recommended solution:* Per-user short-TTL cache (60–120 s) of the assembled payload; `select_related`/`prefetch_related` throughout; office-wide (non-sensitive) analytics from materialized views refreshed on a schedule; `assertNumQueries` on the dashboard.
4. *Fix before Phase 1?* No — but keep the dashboard OUT of `core` and design selectors with this in mind.

---

**O2 — `for_user` scoping via M2M (`supporting_lawyers`) can be slow if written naively.** — LOW
1. *Problem:* Row-by-row `EXISTS` on an M2M in a list view.
2. *Why it matters:* Slow case lists for lawyers on many matters.
3. *Recommended solution:* Write scopers as a single `filter(Q(assigned_lawyer=u) | Q(caselawyer__lawyer=u)).distinct()` or a subquery `EXISTS`, never Python-side; index the through table.
4. *Fix before Phase 1?* No (pattern note).

---

### P. Future maintainability / extensibility

---

**P1 — "Single-tenant now, tenancy-ready later" is mostly wishful without a tenant FK.** — HIGH (decision)
1. *Problem:* "Tenancy-ready" without an `Office`/`Tenant` FK on every table is a slogan. The real choice is: add the FK now (cheap: one model, one middleware, one manager mixin, disciplined queries) **or** genuinely accept a large migration + re-scoping later.
2. *Why it matters:* Adding a tenant discriminator to every table **after** data exists, plus reworking every `for_user` into tenant-aware scoping, is one of the most expensive refactors possible.
3. *Recommended solution:* Get a definitive answer. If SaaS/multi-office is even plausibly on the roadmap → add `Office` + FK + `TenantScopedModel` from Phase 1. If it's genuinely one office forever → **delete all "tenancy-ready" language** and don't carry the cost or the pretense.
4. *Fix before Phase 1?* **Decision yes.**

---

**P2 — Over-generalizing "configurable choices".** — MEDIUM
1. *Problem:* Spec §23 asks only that **case types** become configurable. The plan risks turning every enum (status, priority, stage, hearing_type, document_type, expense_category, contract_type) into a table + admin UI.
2. *Why it matters:* A generic "lookup framework" is over-engineering (§298, §300); it complicates queries, migrations, and reports.
3. *Recommended solution:* `CaseType` = a table (per spec). Everything else stays `TextChoices` until a concrete, stated need. No generic lookup framework.
4. *Fix before Phase 1?* No — but state the principle in the architecture doc.

---

**P3 — Case identity fields are ambiguous.** — MEDIUM (Phase 3)
1. *Problem:* §22 lists `case_number` **and** `internal_reference` with no definitions. A case really has: our file number (ours, auto), the court's docket number (theirs, manual), possibly an opponent's reference.
2. *Why it matters:* Users will put court numbers in the "our number" field; uniqueness/search break.
3. *Recommended solution:* `file_number` (ours, auto, unique), `court_case_number` (theirs, manual, nullable, non-unique, indexed); drop or repurpose `internal_reference`. Confirm with the owner.
4. *Fix before Phase 1?* No.

---

**P4 — Security & audit scheduled as Phase 12, performance as Phase 13.** — HIGH (contradiction with §54/§79)
1. *Problem:* Treating security/audit/performance as *phases* implies 11 phases of code that a later phase must retrofit. The spec itself says security is "first-class" (§54), audit events include Phase-1 actions like "User created" (§46), and §79's Definition of Done already lists "security reviewed / performance reviewed / permissions tested" **per phase**.
2. *Why it matters:* Retrofitting authz/audit across a live schema is where projects rot.
3. *Recommended solution:* Reframe **Phases 12 and 13 as hardening/review passes**, and make "authorization enforced + audit wired + Tier-1 tests + query-count checks" part of **every** phase's DoD. Phase 1 establishes the baseline; each phase extends it. Confirm this reading matches the owner's intent.
4. *Fix before Phase 1?* **Decision/framing yes.**

---

## PART 2 — CONTRADICTIONS BETWEEN SPEC AND PROPOSED ARCHITECTURE (consolidated)

| # | Contradiction | Resolution |
|---|---|---|
| X1 | §9 stack lists **no async worker**, but §14 (reset email), §32 (overdue), §37 (contract expiry), §45 (notifications), §44 (PDF) all need scheduled/background work. | **Decide the async story before Phase 1** (affects compose + deploy). Recommend `django-q2` (DB broker, one `qcluster` container, no Redis). |
| X2 | §31 lists `متأخرة` (overdue) as a stored **Task status**; §32 says overdue is **computed** server-side. Same for §39 invoices. | Overdue = **computed** property + filter + dashboard bucket; stored enums exclude it. Documented deviation — needs owner sign-off. |
| X3 | §13 gives User a single `role`; §12 + §46 ("Permission changed") imply composable, editable permissions. | **Django Groups** as source of truth (multi-group). `role` dropped or derived. Documented deviation. |
| X4 | §15 mandates strict per-object siloing; §17/§43 dashboards/reports imply office-wide visibility. | Per-role visibility matrix (list/detail/fields/aggregates). Recommend office-wide lists + gated details/fields; strict siloing only if explicitly wanted. |
| X5 | §57 "no casual cascade delete" + §21/§26 "show all related history" + §55 "normalized, proper FKs" vs universal soft-delete. | Restricted soft-delete set; "archive = status" for Case/Client; full unique indexes on reference numbers. ADR. |
| X6 | §11 names `core/` and `calendar/`; plan renamed to `common/` and `agenda/`. | Revert to `core/`; keep `agenda/` (stdlib clash) as a recorded ADR. |
| X7 | §34 Documents (Phase 6) reference Contract (Phase 7) and Invoice (Phase 8) which don't exist yet. | Phase 6 `Document` gets `case`/`client` FKs only; `contract`/`invoice` FKs added in Phases 7/8. |
| X8 | §13 "don't collect unnecessary sensitive data" vs §20 `national_id` + `registration_number`. | Make them **optional**, justify collection, decide encryption (D1) before Phase 2. |
| X9 | §16 nav has office-level "الأطراف" (Parties) under Cases; §27 parties are per-case. | Both: an office-wide `Party` directory + per-case `CaseParty` link (helps future conflict checks). Phase 3. |
| X10 | §63 "don't waste effort on i18n where unneeded" vs building `gettext` everywhere for an Arabic-only product. | Get a firm English yes/no; default = commit to `gettext` (lowest regret). |
| X11 | §9 "DRF where useful" / §88 "if APIs required" vs any early DRF. | **No DRF** until a concrete external consumer exists. (Plan already agrees — keep it.) |
| X12 | §60 exhaustive testing vs §298 "don't over-engineer" + solo build. | Tiered test policy (M1). |

---

## PART 3 — DECISIONS I RECOMMEND (my calls, with rationale)

| ID | Decision | Recommendation | Deviates from spec? | Needs your sign-off? |
|---|---|---|---|---|
| R1 | Tenancy | **Single-tenant, drop "tenancy-ready" language** — unless you foresee multi-office SaaS, in which case add `Office` FK in Phase 1. | — | **Yes** |
| R2 | Jurisdiction | Build jurisdiction-agnostic (optional free-text IDs, configurable tax rate, Gregorian primary) until you name the country. | — | **Yes** (country) |
| R3 | Second language | Commit to `gettext` now (low regret) unless "Arabic only, forever". | Tightens §63 | **Yes** |
| R4 | Login identifier | `username`/employee-code as `USERNAME_FIELD`; `email` unique-if-present; phone optional. | Clarifies §13 | **Yes** |
| R5 | User base class | Subclass `AbstractUser`. | — | No |
| R6 | RBAC model | Django **Groups** = source of truth; 5 seeded groups; capability map; `role` dropped (or read-only derived). | **Yes** (§13) | **Yes** |
| R7 | Group→permission seeding | Idempotent `sync_roles` command (not data migrations); CI drift check. | — | No |
| R8 | Async infrastructure | `django-q2` from Phase 1 (`qcluster` compose service; DB broker; no Redis). | **Yes** (§9) | **Yes** |
| R9 | "Overdue" | Computed, not stored; status enums exclude it. | **Yes** (§31/§39) | **Yes** |
| R10 | Object-denial response | **403** default; 404 only under strict siloing. | — | Tied to R11 |
| R11 | Case visibility | Office-wide lists + aggregates for all staff; edit + confidential/financial fields gated by role/assignment. | Interprets §15 vs §17/§43 | **Yes** |
| R12 | Confidential fields | Separate `CaseConfidential` 1:1 model (Phase 3); single `for_display(user)` projection. | — | Confirm approach |
| R13 | Audit mechanism | `django-auditlog` + actor middleware + explicit event logging + field allowlist for diffs + no-delete; DB trigger in Phase 12. | — | No |
| R14 | Dev environment | Fully Dockerized (`web` + `db` + `qcluster`); Windows = editor host only. | — | No |
| R15 | Postgres | PG 16; `pg_trgm` + `unaccent` via `CreateExtension` (Phase 1); ICU collation for Arabic sort. | — | No |
| R16 | RTL | Tailwind 3.4 logical utilities, no RTL plugin; `<bdi>` wrappers in component kit; **Western digits** for money/IDs. | — | Confirm digits |
| R17 | MFA | Install `django-otp` + TOTP in Phase 1; enrollment UI + per-user opt-in; enforcement setting-gated, default on for office managers; full rollout decision Phase 12. | — | Confirm default |
| R18 | Reference numbers | `NumberSequence(scope, period, last_value)` + `select_for_update`; gaps accepted for case/client; invoice numbers assigned at issue; ADR before Phase 2; concurrency test required. | — | Confirm gap-free invoice need |
| R19 | Soft-delete | Restricted named set; "archive = status" for Case/Client; full unique indexes on reference numbers; ADR before Phase 2. | Interprets §57 | Confirm approach |
| R20 | Security/audit/perf | Phases 12/13 become **hardening passes**; authz + audit + Tier-1 tests + query-count checks are in **every** phase's DoD. | Reframes §82 | **Yes** |
| R21 | App layout | Phase 1 creates only `core`, `accounts`, `audit`; `core` (not `common`); `agenda` for calendar (ADR); services/selectors only where justified. | Reverts a deviation | No |
| R22 | CI / VCS | GH Actions with PG service + `makemigrations --check` + `pip-audit` + secret scan + `check --deploy`; pre-commit; rename `master`→`main`; `phase/N-*` branches → PR → `main`. | — | No |
| R23 | Money models | `currency` field on all financial models; `ROUND_HALF_UP` 2dp policy (ADR); issued invoices immutable. | Fills §39/§42 gaps | Confirm invoice immutability |
| R24 | Field encryption | DB-volume encryption baseline; application-level encryption for `national_id` — **your call**. | — | **Yes** |
| R25 | Password reset | Django email reset **+** admin "issue temporary password (force change)"; console email backend in dev. | — | Confirm dev-only email OK |

---

## PART 4 — REVISED ARCHITECTURE (deltas from `QISTAS_PHASE_0_ANALYSIS.md`)

Everything in the Phase 0 doc stands **except**:

1. **Apps:** `core/` (not `common/`). Phase 1 creates `core`, `accounts`, `audit` **only**. `agenda/` (calendar) rename recorded as an ADR. Later apps created at their phase. `dashboard` app appears in Phase 9; Phase 1's landing page is a `core` view.
2. **Layering:** the one enforced early pattern is **permission-scoped querysets/managers** + view mixins. `services.py` only for multi-step transactional flows; fat models + forms elsewhere.
3. **User & RBAC:** `AbstractUser` subclass; identifier = `username`/employee-code (pending R4); **Groups drive authorization** (pending R6), seeded + kept in sync by an idempotent `sync_roles` command. Capability map keyed by group.
4. **Authorization enforcement:** `for_user(user)` is an explicit queryset method; a `ScopedQuerySet` + view mixins that *require* it; DEBUG assertion + tests. **403** on denial by default.
5. **Confidential data:** sensitive case fields move to a `CaseConfidential` 1:1 model (Phase 3); a single `for_display(user)` projection is the only rendering path.
6. **Audit:** `django-auditlog` + actor middleware + explicit `log_event()` for non-ORM events; **field allowlist** for value diffs (sensitive fields logged as "changed" only); audit views enforce the same permissions as the record; no admin delete; DB trigger deferred to Phase 12.
7. **Async:** add `django-q2` + a `qcluster` compose service from Phase 1 (pending R8). Password-reset email, overdue recompute (if needed), notifications, contract-expiry scans, PDF all run here.
8. **Dev/prod parity:** the **app runs in Docker** in dev (`web` + `db` + `qcluster`), code bind-mounted; CI mirrors it; tests target Postgres.
9. **Postgres:** PG 16 pinned; `pg_trgm` + `unaccent` enabled via migration in Phase 1; ICU collation for Arabic text.
10. **RTL/i18n:** Tailwind 3.4 logical utilities (no plugin); `<bdi>`/`{% num %}` in the component kit; Western digits for money/IDs; `gettext` committed (pending R3); `FORMAT_MODULE_PATH` set explicitly; Hijri decision tied to jurisdiction.
11. **Auth hardening:** `django-axes` locks by **username only**; sliding idle-timeout middleware (env-configurable); `django-otp` installed with setting-gated enforcement; admin temporary-password action alongside email reset.
12. **Money (Phase 8, noted now):** `currency` field everywhere; rounding ADR; issued invoices immutable; `PaymentReversal` modeled; optimistic locking on financial (and case) edit forms.
13. **Reference numbers:** `NumberSequence` table pattern; ADR + concurrency test before Phase 2.
14. **Deletion:** restricted soft-delete set; archive-as-status for Case/Client; full unique indexes on numbers; ADR before Phase 2.
15. **Process:** Phases 12/13 reframed as hardening passes; per-phase DoD includes authz + audit + Tier-1 tests + query-count checks (pending R20).
16. **VCS/CI:** `master`→`main`; `phase/N-*` branch → PR → CI (PG service, lint, tests, `makemigrations --check`, `check --deploy`, `pip-audit`, secret scan) → `/code-review` → merge; pre-commit hooks.

---

## PART 5 — REVISED PHASE 1 PLAN

**Phase 1 — Foundation.** Goal: a Dockerized, secure, RTL Django shell a user can log into, with the authorization + audit + async + test + CI baselines in place, and **zero domain entities**.

### 1.1 Pre-work — ADRs & decisions (no code)
Write `docs/architecture.md` + `docs/adr/`:
- ADR-001 Tenancy (R1) · ADR-002 Language/i18n (R3) · ADR-003 Login identifier & User base (R4/R5) · ADR-004 RBAC = Groups (R6) · ADR-005 Async = django-q2 (R8) · ADR-006 "Overdue" computed (R9) · ADR-007 Object-denial 403 & visibility matrix (R10/R11) · ADR-008 Audit mechanism (R13) · ADR-009 Soft-delete & archival policy (R19) · ADR-010 Reference-number strategy (R18) · ADR-011 `on_delete` policy table (G2) · ADR-012 RTL & numerals (R16) · ADR-013 Security/audit/perf as per-phase DoD (R20) · ADR-014 Test tiers (M1) · ADR-015 `agenda` rename.
- Resolve the **PART 6** decisions with the owner first.

### 1.2 Project scaffold
- `pyproject.toml` (pinned): Django 5.2 LTS, `psycopg[binary]`, `django-environ`, `whitenoise`, `django-axes`, `django-otp`, `django-auditlog`, `django-q2`, `django-htmx`, `pytest-django`, `factory-boy`, `faker`, `coverage`, `ruff`, `pip-audit`.
- `qistas/settings/{base,dev,prod,test}.py`; `.env.example`; root `.gitignore`; `manage.py`; `wsgi/asgi`.
- **Docker:** `Dockerfile` (Linux, non-root), `docker-compose.yml` → `web`, `db` (postgres:16), `qcluster`; named `media` volume; code bind-mount; `compose` docs in `README.md`.
- `settings/test.py` → Postgres; `settings/prod.py` → secure cookies, HSTS, headers, `check --deploy` clean.
- Migration enabling `pg_trgm` + `unaccent`.
- **CI** (`.github/workflows/ci.yml`): PG 16 service; `ruff` + `ruff format --check`; `pytest` + coverage; `makemigrations --check --dry-run`; `check --deploy`; `pip-audit`; `gitleaks`. `.pre-commit-config.yaml` mirrors it.
- Rename `master`→`main`; first commit adds `.gitignore` + `.env.example` + scaffold.

### 1.3 `core` app
- Base models: `TimeStampedModel`, `AuthoredModel`; `SoftDeleteModel` + `SoftDeleteManager` **applied to nothing yet** but available per ADR-009.
- `core/permissions/`: `capabilities.py` (group→capability map), `ScopedQuerySet`/`ScopedManager` base + `for_user` contract, `ScopedDetailMixin`/`ScopedListMixin` (require scoping, 403 on denial), `GroupRequiredMixin`, DEBUG scoping assertion.
- `core/numbering.py`: `NumberSequence` model + `next_number(scope, period)` (transaction-safe) — **framework only**, no consumers.
- Pagination helper; `core/context_processors.py` (nav); template tags: `{% can %}`, `{% num %}` (bidi-safe number/identifier), badge, empty-state.
- Error views + templates: 400/403/404/500 (themed, Arabic, RTL).
- Authenticated landing view (`/`) with real Arabic empty-states (placeholder for the Phase 9 dashboard).

### 1.4 `accounts` app
- `User` (`AbstractUser` subclass): identifier field per ADR-003, `phone`, timestamps; `email` unique-if-present.
- `Group` seeding: migration creates the 5 groups (rows only); `sync_roles` management command owns group→permission mapping (idempotent; CI asserts no drift).
- Auth flows (Django built-ins, themed, Arabic, RTL): login, logout, password change, password reset (request/email/confirm/complete) **+** admin action "issue temporary password (force change on next login)". Console email backend in dev.
- `django-axes`: lockout by **username**, threshold/cooloff via env, Arabic lockout page, admin unlock, audited.
- `django-otp` + TOTP: enrollment UI, per-user opt-in, enforcement middleware behind `REQUIRE_MFA` (default: office-manager group only).
- Sliding **idle-timeout** middleware (env-configurable); project-wide `LoginRequiredMiddleware` (allowlist: auth, errors, static, health).
- `django-auditlog` actor middleware wired.

### 1.5 `audit` app (minimal but correct)
- `AuditLog` model per §46 (actor `SET_NULL`, action, entity_type, entity_id, `object_repr` sanitized, `changes` JSON, ip, user_agent, created_at); indexes on `created_at`, `(entity_type, entity_id)`, `actor`.
- `log_event(request, action, obj=None, changes=None)` helper.
- Auth signal receivers: login, logout, login-failed, lockout, password change/reset, user created, group membership change.
- Field-diff **allowlist** infrastructure (sensitive fields → "changed" without values).
- Admin: registered **read-only**, delete disabled. (DB trigger deferred to Phase 12 — noted in ADR-008.)

### 1.6 UI foundation
- **Tailwind standalone CLI** (no Node app); `static/src/app.css` → `static/css/app.css`; build script + `README`.
- Design tokens (navy / dark slate / warm off-white / neutral gray / bronze) as CSS vars + Tailwind theme; **self-hosted IBM Plex Sans Arabic** (`font-display: swap`, subset, `unicode-range`).
- `templates/base.html`: `<html lang="ar" dir="rtl">`, right sidebar, topbar, toast region, **HTMX + Alpine vendored** into `static/vendor/`, global `hx-headers` CSRF wiring.
- Component partials (`templates/components/`) for the §49 kit — RTL-native via logical utilities, `<bdi>` for numbers/identifiers. Dev-only `/styleguide` page rendering all of them.
- **Permission-aware navigation** from a data-driven config, filtered by the capability map, mobile-collapsible (Alpine).

### 1.7 Testing foundation (Tier-1 harness)
- `pytest.ini`/`pyproject` config, `conftest.py`, `UserFactory` (+ group fixtures), `tests/utils.py`: `assert_login_required`, `assert_forbidden` (403), `assert_not_found`, `assertNumQueries` wrapper, a concurrency helper (`run_concurrently`) for the numbering test later.
- Phase 1 tests:
  - **Auth:** login ok / bad password / inactive; logout; password-change requires auth; reset token flow; admin temp-password action; axes lockout by username (and *not* by IP); session cookie flags (prod settings); idle timeout; MFA enrollment + setting-gated enforcement.
  - **Authz framework:** `capabilities.can()` truth table per group; `GroupRequiredMixin` allow/deny; `ScopedListMixin`/`ScopedDetailMixin` + a throwaway model prove `for_user` scoping and 403-on-denial; DEBUG assertion fires when scoping is skipped.
  - **Navigation:** items shown/hidden by capability.
  - **Errors:** 400/403/404/500 render themed templates with `DEBUG=False`.
  - **Audit:** login/logout/failed-login/user-created/group-change write `AuditLog`; `AuditLog` delete blocked; sensitive-field diff suppressed by the allowlist.
  - **Numbering:** `next_number` basic + a **concurrent** test (no duplicates, no lost increments).
  - **Smoke:** `check --deploy` clean; migrations apply on a fresh PG; `pg_trgm`/`unaccent` present.

### 1.8 Project tracking & docs
- `PROJECT_STATUS.md` (§78) with all 14 phases; Phase 1 = COMPLETED / PENDING APPROVAL on completion.
- Refresh `.wolf/STATUS.md` via `/handoff`.
- `docs/architecture.md` (app roadmap, layering principles, test tiers, security baseline) + the ADRs.

### 1.9 Phase 1 Definition of Done
Migrations apply on clean PG · all Phase 1 (Tier-1) tests green · `check --deploy` clean on prod settings · full stack runs via `docker compose up` · login → landing → logout works · MFA enrollable, enforcement setting-gated · nav filters by capability · themed error pages with `DEBUG=False` · RTL + bidi verified visually against mixed Arabic/Latin/number data · `qcluster` runs and processes a trivial test task · CI green · `master`→`main` done, work on a `phase/1-foundation` branch with an open PR · `/code-review` + auth security review complete, Critical/High fixed · every decision recorded as an ADR · `PROJECT_STATUS.md` + `.wolf/STATUS.md` updated.
Then **Phase Completion Report (§76) → STOP.**

### 1.10 Explicitly OUT of Phase 1 (Deferred Items)
All domain models (Client/Case/Court/Hearing/Task/Document/Contract/Invoice/Payment/Notification); the real dashboard; DRF; reports; global search implementation; PDF; notification content/scanners; demo data; the audit DB-trigger; MFA org-wide enforcement; X-Accel download path; field-level encryption implementation (decision only).

---

## PART 6 — DECISIONS THAT GENUINELY NEED YOUR INPUT

**Blocking Phase 1 (I cannot responsibly pick these for you):**

1. **Tenancy (R1):** one office per deployment, or multi-office SaaS on the roadmap? (Determines whether every table gets an `Office` FK now.)
2. **Jurisdiction / country (R2):** which country's legal system? (National-ID formats, court hierarchy, tax model, **Hijri calendar** expectations.)
3. **Second language (R3):** will Qistas ever need English (or any non-Arabic) UI? Yes / No / Unknown.
4. **Login identifier (R4):** do all staff have individual work emails, or should login be a username/employee-code?
5. **Async infrastructure (R8):** OK to add `django-q2` (one extra container, no Redis) to the stack now? It's a deviation from §9's stack list but 4+ later phases need scheduled work.
6. **"Overdue" as computed, not a stored status (R9):** OK to diverge from the literal §31/§39 enums?
7. **RBAC via Groups instead of a `role` field (R6):** OK to diverge from §13's `role` field (users can then hold multiple roles)?
8. **Case visibility model (R11):** do all staff see all office cases in lists/aggregates (details/fields gated), or are lawyers strictly siloed to their assigned cases (per the literal §15 example)?
9. **Field-level encryption (R24):** is application-level encryption of `national_id` (and similar) a requirement, or is DB-volume encryption sufficient for v1?
10. **Process reframing (R20):** confirm Phases 12/13 become hardening passes and security/audit/tests are per-phase DoD (matches §79) rather than deferred.

**Needed before their phase (not Phase 1), flagging now:**

11. **Gap-free invoice numbers (R18):** does your jurisdiction/accountant require strictly gap-free invoice numbering? (Changes the numbering design.)
12. **Issued-invoice immutability (R23/F1):** confirm that once an invoice is issued, its line items/amounts are frozen and corrections are credit notes.
13. **"رسوم القضايا" / case fees (spec §16, Phase 8):** is this a fee **agreement** (retainer / hourly / contingency / fixed) that generates invoices, or just an expense category? Needs a product definition.
14. **Conflict-of-interest / privilege (D3):** in scope for v1 at all, or explicitly deferred?
15. **Client portal:** confirmed **out of scope** (clients never log in)? 
16. **Numerals (R16):** Western digits (0-9) for money and IDs — acceptable? (Recommended for legal/financial clarity.)
17. **MFA default (R17):** enforce MFA for office managers from Phase 1, opt-in for everyone else, full enforcement decided at Phase 12 — acceptable?

---

---

## PART 7 — FINAL LOCKED DECISIONS (owner sign-off 2026-09-08)

All PART 6 decisions are now resolved. Each is recorded as an ADR under `docs/adr/` and folded into `docs/architecture.md` and `docs/PHASE_1_PLAN.md`.

| PART 6 / topic | Final decision | ADR |
|---|---|---|
| 1. Tenancy | **Single-tenant, one office per deployment.** No `Office` FK anywhere in Phase 1. Multi-tenancy is a documented future migration. | ADR-0001 |
| 2. Jurisdiction | **Palestine.** Jurisdiction-specific rules kept extensible; **not** built out in Phase 1. | ADR-0002 |
| 3. Second language | **Yes — i18n-ready architecture from day 1** (`gettext`, `LocaleMiddleware`, `locale/`). Ships `ar` only; Phase 1 UI is Arabic-first. English is a later catalog. | ADR-0003 |
| 4. Login identifier | **Work email is the primary login identifier.** No `username` as identifier. Employee-code kept as an extension point. | ADR-0004 |
| 5. Async infrastructure | **No `django-q2`, no Redis, no worker in v1.** Time-based work = idempotent Django management commands + system cron. Seam documented (`core.tasks`). | ADR-0005 |
| 6. "Overdue" | **Approved — computed state, not a stored status.** | ADR-0006 |
| 7. RBAC | **Django Groups + centralized capability layer.** Users may belong to multiple groups. No single `role` field as source of truth. Capability layer centralized + testable. | ADR-0007 |
| 8. Case visibility | **v1: lawyers see all office cases.** Internal/legal notes + financial fields are **separately permission-gated**. Object-level authorization still enforced. **No** strict lawyer-to-assigned-case siloing in v1. | ADR-0008, ADR-0019 |
| 9. Field-level encryption | **No application-level encryption in v1.** Rely on DB/volume/storage encryption + secure handling. `national_id` & similar = highly sensitive: never in logs, never exposed unnecessarily, permission-restricted, not trigram-indexed / not in global search. Extension point left for app-level encryption. | ADR-0009 |
| 10. Process reframing | **Approved.** Phases 12/13 are hardening/review passes. Security, audit, testing, accessibility, performance are in the DoD of **every relevant phase**. | ADR-0010 |
| 11. Invoice numbering | **Gap-free numbering NOT required for v1.** Transaction-safe unique invoice references. No legal-numbering over-engineering. | ADR-0011, ADR-0021 |
| 12. Issued invoices | **Immutable.** Corrections via a proper correction/credit-note mechanism. Full workflow built in the **Finance phase**, not Phase 1. | ADR-0012 |
| 13. رسوم القضايا | **`FeeAgreement` / agreed legal fee with the client.** Not modelled as an Expense. Detailed structure finalized in the Finance phase. | ADR-0013 |
| 14. Conflict of interest | **Out of scope for v1.** Deferred feature. | ADR-0014 |
| 15. Client portal | **Out of scope for v1.** Deferred feature. | ADR-0015 |
| 16. Digits | **Western digits** for IDs, references, dates (where technically appropriate) and monetary values. Arabic UI text stays RTL. No forced Arabic-Indic digits. | ADR-0016 |
| 17. MFA | **Enrollable in Phase 1. NOT enforced globally.** Not mandatory for office managers yet. Enforcement decided in the security hardening phase. | ADR-0017 |

**Additional architectural rules locked (owner):** Phase 1 adds **no** domain models, **no** DRF, **no** `django-q2`, **no** Redis, **no** real dashboard, **no** finance logic, **no** client/case/hearing/document domain models. Phase 1 is strictly Foundation.

**Grill findings now resolved by the above:** B1→ADR-0007 · B2→ADR-0004 · C1→ADR-0019 · C3/C4→ADR-0008 · D1→ADR-0009 · E1/E2→ADR-0020 · F1→ADR-0012 · G1→ADR-0022 · H1→ADR-0011/0021 · J1→ADR-0003 · J4→ADR-0016 · K1→ADR-0023 · L1→ADR-0017 · P1→ADR-0001 · P4→ADR-0010 · X1→ADR-0005 · X2→ADR-0006 · X3→ADR-0007.

**Grill findings still open but NOT blocking Phase 1** (scheduled to their phase, tracked in `docs/architecture.md` §Deferred): B5, C5, D3, D5, F2, F4, F5, I3, P2, P3, X9 (party directory).

### No unresolved BLOCKING decision remains for Phase 1.

---

**STOP.** Documentation only — no implementation, no migrations, no models. Awaiting explicit **`APPROVE PHASE 1`**.
