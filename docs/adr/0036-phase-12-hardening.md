# ADR-0036 — Phase 12 hardening: findings and the patterns they generalize to

Status: **Accepted** 2026-09-11 (owner: Khaled; architect: Claude)
Phase: 12
Builds on: every prior ADR — this phase re-audits, not re-designs. No new
app, model, or product feature.

## Context

Phase 12 is the spec's dedicated hardening pass: a project-wide security,
authorization, performance, and integrity review of Phases 1–11, explicitly
tasked with *not* trusting each phase's own self-review. It is not a feature
phase — the product surface is unchanged; only defects found during the audit
are fixed.

## Scope of the audit

Authentication · authorization (capability + object-level) · CSRF/XSS/SQLi ·
IDOR/URL tampering · mass assignment · file/document security · financial
integrity + concurrency · mixed-currency handling · audit-log integrity ·
notification authorization · report authorization · dashboard authorization ·
N+1/query-count regressions · database integrity (`on_delete`, constraints,
indexes) · transaction boundaries · session/cookie/deployment configuration ·
dependency vulnerabilities · error/information leakage. Method: read every
domain's views/forms/services/selectors/models fresh; grep the whole tree for
known-dangerous patterns (`Model.objects.get(pk=request...)`, `|safe`,
`mark_safe`, `.raw()`, `csrf_exempt`, `autoescape off`); trace every mutating
endpoint's decorator chain; re-derive the finance/notification/report/
dashboard isolation boundary from the HTTP layer rather than trusting the
selectors' own docstrings.

## Findings

### 1. `InvoiceUpdateView` leaked invoice existence + issued-status to non-finance users (Medium–High) — FIXED

`finance/views.py::InvoiceUpdateView.dispatch()` fetched the invoice, then —
for an **issued** (non-draft) invoice — returned `redirect(...)` *inside* the
`if request.user.is_authenticated:` block, **before** calling
`super().dispatch()`. `CapabilityRequiredMixin.dispatch()` (the `finance.view`
gate) lives further up the MRO and is only reached via that `super()` call, so
for this one branch it never ran. Every other `*UpdateView.dispatch()`
override in the project (`cases`, `contracts`, `courts`, `documents`,
`hearings`, `tasks`, `clients`) unconditionally falls through to
`super().dispatch()`; `InvoiceUpdateView` was the sole exception. Net effect:
a **paralegal** (zero finance access) requesting `/finance/invoices/<pk>/edit/`
for an issued invoice got a **302** to the detail page instead of a **403** —
leaking "this invoice id exists and is issued" through the response status and
`Location` header, an authorization-check-ordering bug in the one domain the
spec repeatedly singles out for isolation (ADR-0032).

**Fix:** moved the draft-state guard out of `dispatch()` into `get()`/`post()`
overrides — mirroring the already-safe `hearings._HearingActionMixin.
_guard_open()` pattern, which runs only after `View.dispatch()` (and therefore
`CapabilityRequiredMixin`) has already executed. `dispatch()` now only fetches
the scoped object; it never branches or redirects. Regression tests:
`finance/tests/test_invoices.py` (both a draft and an issued invoice now 403
identically for a paralegal; a POST also 403s; the legitimate redirect for an
authorized user on an issued invoice — and the legitimate 200 for a draft —
are both still verified) and `tests/test_capability_boundary_sweep.py`.

### 2. `ClientForm` let `status` (archive/restore) through the general edit path (Medium) — FIXED

`clients.ClientForm.Meta.fields` included `"status"`, and `ClientUpdateView`
passed `form.cleaned_data` straight to `update_client(data=...)`, which applied
it with no transition guard and logged only the generic `CLIENT_UPDATED`
action. Every other status-bearing domain in the app (`CaseForm`,
`ContractForm`, `HearingUpdateForm`, `Task`/`Deadline` status) deliberately
keeps `status` **off** the general edit form — status changes go through a
dedicated, audited action (`change_status`, `archive_client`/`restore_client`,
etc.). Clients was the one place this rule wasn't enforced: a
`clients.manage` holder could silently archive or restore a client as a side
effect of an unrelated edit, with **no `CLIENT_ARCHIVED`/`CLIENT_RESTORED`
audit event** — a gap in the audit trail the dashboard's recent-activity feed
and any future reporting on archival specifically rely on (§46, §12 of this
phase's brief). Not a capability bypass (the same `clients.manage` is
required either way) — an audit-integrity and data-integrity gap.

**Fix:** `ClientForm.__init__` pops the `status` field when editing an
existing instance (create keeps it — the model default is `active`, and
choosing `prospect` at intake is a legitimate, existing use). Defense in
depth: `clients.services.update_client` now strips any `status` key from
`data` unconditionally, so even a caller that bypasses the form cannot smuggle
a status change through this path — status changes only ever happen through
`archive_client` / `restore_client`. The edit template shows a read-only
status line + a pointer to the client page's archive/restore action when the
field isn't present. Regression tests in `clients/tests/test_views.py` (HTTP:
a smuggled `status=archived` in the POST body is silently ignored, the real
field edit still applies) and `clients/tests/test_audit.py` (service layer:
same, plus the audit diff never contains `"status"`).

### 3. Everything else audited and confirmed sound — no change

- **Mass assignment:** every `ModelForm.Meta.fields` in the project is an
  explicit allowlist (no `__all__`, no `exclude`); none include a
  server-controlled field (`*_number`, totals, `amount_paid`, `sha256`,
  `uploaded_by`, `created_by`, audit actor, notification `recipient`/`url`).
  Money-bearing forms (`PaymentForm`, `PaymentReversalForm`, `CreditNoteForm`,
  `IssueInvoiceForm`) are plain `forms.Form`, never `ModelForm` — every
  monetary write is server-computed in `finance.services`.
- **IDOR / IDOR-object-scoping:** every list/detail/action view resolves its
  object through a `for_user()`-scoped queryset + `get_object_or_404` (or the
  equivalent `_get_<x>` helper), verified with `assert_scoped`. The two
  genuinely per-user/per-capability siloed boundaries — `notifications`
  (per-recipient, `Notification.objects.for_user`, **404** on tamper — already
  exhaustively tested in Phase 11) and `finance` (capability-gated, not
  object-siloed — paralegal has zero access, not "sees fewer rows") — hold.
  `cases.view_confidential` gating (`CaseConfidentialUpdateView`) is correctly
  ordered (no repeat of finding #1). One project-wide regression file added:
  `tests/test_capability_boundary_sweep.py` — every finance GET/POST URL,
  every financial report page+CSV, the dashboard financial-overview context
  keys, the agenda's calendar events, and `invoice_overdue` notification
  generation, exercised against a paralegal at the HTTP layer in one place —
  so a future finance URL added without the gate fails loudly here.
- **XSS:** the only two `|safe`/`mark_safe` uses in the codebase are
  `qistas.active()`'s `css` kwarg (a literal the *template author* supplies,
  never request data) and the MFA QR SVG (`qrcode.image.svg.SvgPathImage`
  encodes the `otpauth://` URI into path geometry, never echoes it as text).
  No `{% autoescape off %}` anywhere.
- **SQL injection:** no `.raw()`, `.extra()`, or `cursor.execute()` in
  application code (one `cursor.execute` exists, in a test that only reads
  `pg_extension`). ORM-only throughout.
- **CSRF:** no `@csrf_exempt` in the project; every mutating function view is
  `@require_POST` (or internally method-gated, e.g. `mfa_disable`).
- **Document security:** private storage confirmed to genuinely 404 at both
  `/media/documents/<real-path>` and `/media/<real-path>` (existing
  regression, re-verified); filenames are sanitized on both upload
  (`_safe_original_name`) and download (`Document.download_filename` — CR/LF/
  quote/backslash stripped, path-segment stripped, length-capped) so no header
  injection or path traversal; magic-byte validation + extension agreement
  unchanged.
- **Finance integrity & concurrency:** every money-mutating function is
  `@transaction.atomic`; every function that must serialize against concurrent
  writes takes `Invoice.objects.select_for_update()` on the invoice row before
  reading the balance it will validate against (`record_payment`,
  `reverse_payment`, `issue_credit_note`) — re-derived from the code, not
  assumed. DB `CheckConstraint amount_paid <= total` is a real backstop.
  `Decimal` end to end via `core.money.quantize`; no float arithmetic found
  anywhere in the codebase.
- **Mixed currency:** every aggregation point (`finance.selectors.
  _invoice_totals_by_currency`, `firm_financials`, all five financial report
  builders, the dashboard's financial overview) groups by currency and never
  sums across currencies — re-confirmed by reading the code, not by trusting
  the prior phases' tests (which also still pass).
- **Audit integrity:** `AuditLog`'s own queryset/model raise `PermissionError`
  on `.update()`/`.delete()`; its `ModelAdmin` denies add/change/delete
  unconditionally. django-auditlog's `LogEntry` admin is registered with the
  library's own delete-permission gate (real Django permission check,
  reachable only through `is_staff`, which Qistas never grants to a regular
  role — only `is_superuser` accounts get it, architecture.md §5). No
  passwords/tokens/national IDs/document bytes/legal notes/financial bodies/
  notification bodies are logged (verified against `core.sensitive.
  SENSITIVE_FIELDS` and each domain's `AuditLog` `changes=` call sites).
- **Auth/session:** Django's built-in `LoginView`/`login()` is used unmodified
  (session-key rotation on login is Django's default, not overridden);
  `update_session_auth_hash` on password change is the unmodified Django
  default; password reset is Django's enumeration-safe flow, unmodified;
  lockout-by-username (not IP) is a deliberate, documented ADR-0026 decision
  (`axes.W006` is silenced for exactly this reason, re-verified against the
  library's own check source); MFA-pending users are blocked from every
  non-allowlisted view by `MFAEnforcementMiddleware.process_view`.
- **Deployment:** `manage.py check --deploy` run against **`config.settings.
  prod`** with a real 86-char secret, real `ALLOWED_HOSTS`, and real
  `CSRF_TRUSTED_ORIGINS` (the database engine doesn't matter for this check,
  so a SQLite `DATABASE_URL` was substituted to run it without PostgreSQL) —
  **0 warnings, 1 silenced (the intentional `axes.W006`)**. This upgrades the
  "test-settings-only, PG needed" caveat every prior phase carried: the real
  prod settings are now empirically verified clean, not merely inspected.
- **Dependencies:** `pip-audit` clean (no known vulnerabilities); every
  dependency is pinned to an exact version; no upgrade made (none was needed).
- **N+1 / performance:** every existing query-count regression test (10
  across dashboard/reports/notifications) still passes; no new N+1 introduced
  by this phase's changes (both fixes are pure control-flow, no new queries).
- **Database integrity:** `on_delete=CASCADE` occurs only within an aggregate
  root in every model in the project (`CaseConfidential`/`CaseLawyer`/
  `CaseParty`/`CaseNote`/`CaseEvent` → `Case`; `InvoiceLineItem` → `Invoice`;
  `Notification` → its own `recipient` User) — never into `Case`, `Hearing`,
  `Invoice`, `Payment`, `Document`, `Contract`, or `AuditLog`, per ADR-0022.

## Consequences

- Two real, narrowly-scoped defects fixed, each with regression tests that
  fail if the pattern regresses; no other code touched (`git diff --stat`:
  8 files, +297/−4, entirely in `clients/`, `finance/views.py`, one template,
  and new tests).
- `tests/test_capability_boundary_sweep.py` is now the single place that
  future finance/report/dashboard/agenda/notification work must keep green —
  it is deliberately broader than any one phase's own tests so it survives
  refactors across app boundaries.
- The `dispatch()`-early-return anti-pattern (finding #1) is now a named
  Do-Not-Repeat entry (`.wolf/cerebrum.md`): a `dispatch()` override must
  never `return` a response before its final `return super().dispatch(...)` —
  state-dependent guards belong in `get()`/`post()`.
- PostgreSQL/Docker verification remains deferred — same environment blocker
  as every prior phase (no Docker daemon, no `psql`/`psycopg` on this
  machine); documented precisely in `docs/PHASE_12_REPORT.md` with the exact
  commands to run on a capable machine/CI.
