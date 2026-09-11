━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:        12 — Hardening (Audit + Advanced Security)
Status:       COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
              (same environment blocker as Phases 1–11).
Branch:       phase/12-hardening — based on master @ 6a76894 (Phase 11 merge, PR #10)
Design:       docs/adr/0036-phase-12-hardening.md (Accepted)

**This is not a feature phase.** No new app, model, URL, or product surface.
The entire diff is two narrowly-scoped defect fixes plus regression tests —
`git diff --stat`: 10 files changed, all inside `clients/`, `finance/views.py`,
one template, and test files.

════════════════════════════════════════
1. SECURITY AUDIT SCOPE
════════════════════════════════════════

Read fresh (not trusting each phase's own self-review): every view, form,
service, selector, and model across all 15 apps. Grepped the whole tree for
known-dangerous patterns: `Model.objects.get(pk=request...)`, `.filter(...)`
without `for_user`, `|safe` / `mark_safe`, `.raw()` / `.extra()` /
`cursor.execute`, `csrf_exempt`, `{% autoescape off %}`. Traced every mutating
endpoint's decorator/dispatch chain by hand. Re-derived (not re-read) the
finance/notification/report/dashboard isolation boundary from the HTTP layer.
Ran `manage.py check --deploy` against **real** `config.settings.prod` values
for the first time (previously only inspected/deferred).

Covered: authentication, authorization (capability + object-level), CSRF,
XSS, SQL injection, IDOR, mass assignment, file/document security, financial
integrity + concurrency, mixed-currency handling, audit-log integrity,
notification authorization, report authorization, dashboard authorization,
N+1/query-count regressions, database integrity (`on_delete`, constraints,
indexes), transaction boundaries, session/cookie/deployment configuration,
dependency vulnerabilities, error/information leakage.

════════════════════════════════════════
2. VULNERABILITIES FOUND
════════════════════════════════════════

**Finding #1 — `InvoiceUpdateView` authorization-check ordering (Medium–High).**
`finance/views.py::InvoiceUpdateView.dispatch()` fetched the invoice, then, for
an **issued** invoice, `return redirect(...)` *inside* the
`if request.user.is_authenticated:` block — **before** calling
`super().dispatch()`, which is where `CapabilityRequiredMixin`'s `finance.view`
check lives (further up the MRO). Every other `*UpdateView.dispatch()`
override in the project unconditionally falls through to `super().dispatch()`;
this was the sole exception (confirmed by grepping every `dispatch()` override
in the codebase). Net effect: a **paralegal** (zero finance access) requesting
`/finance/invoices/<pk>/edit/` for an issued invoice got a **302** instead of a
**403**, leaking "this invoice id exists and is issued" through the response
status + `Location` header — the one domain the spec repeatedly singles out
for strict isolation (ADR-0032, §98).

**Finding #2 — `ClientForm` mass-assignable `status` (Medium, audit integrity).**
`clients.ClientForm.Meta.fields` included `"status"`; `ClientUpdateView` passed
`form.cleaned_data` straight to `update_client(data=...)`, which applied it
with **no transition guard and no dedicated audit action** (only the generic
`CLIENT_UPDATED`). Every other status-bearing domain (`CaseForm`,
`ContractForm`, hearings, tasks/deadlines) keeps `status` off the general edit
form — status changes go through a dedicated audited action. Clients was the
one place this house rule wasn't enforced: a `clients.manage` holder could
silently archive/restore a client as a side effect of an unrelated edit, with
no `CLIENT_ARCHIVED`/`CLIENT_RESTORED` audit event — an audit-integrity gap
(spec §46/§12), not a capability bypass (the same `clients.manage` is required
either way).

No other vulnerability was found. See §4–16 below for the confirm-sound
walk-through of every other audited area.

════════════════════════════════════════
3. VULNERABILITIES FIXED
════════════════════════════════════════

**Fix #1:** moved the draft-state guard out of `InvoiceUpdateView.dispatch()`
into `get()`/`post()` overrides — mirroring the already-safe
`hearings._HearingActionMixin._guard_open()` pattern, which runs only after
`View.dispatch()` (and therefore `CapabilityRequiredMixin`) has already
executed. `dispatch()` now only fetches the scoped object; it never branches
or redirects. Regression tests: `finance/tests/test_invoices.py`
(`test_issued_invoice_update_view_post_also_redirects`,
`test_draft_invoice_update_view_still_renders`,
`test_paralegal_cannot_probe_invoice_status_via_the_edit_url` — both a draft
and an issued invoice now 403 identically for a paralegal) and
`tests/test_capability_boundary_sweep.py`
(`test_paralegal_403_on_issued_invoice_edit_even_though_it_redirects_for_a_manager`).
buglog bug-118.

**Fix #2:** `ClientForm.__init__` pops the `status` field when editing an
existing instance (create keeps it — a client's model default is `active`,
and choosing `prospect` at intake is a legitimate, pre-existing use — removing
it would have been unrelated scope reduction). Defense in depth:
`clients.services.update_client` now unconditionally strips any `status` key
from `data` before diffing/applying, so even a caller that bypasses the form
cannot smuggle a status change through this path. The edit template shows a
read-only status line pointing at the client page's archive/restore action
when the field is absent (so it doesn't silently disappear with no
explanation). Regression tests: `clients/tests/test_views.py`
(`test_update_cannot_smuggle_a_status_change`,
`test_edit_form_never_renders_a_status_field`) and `clients/tests/test_audit.py`
(`test_update_client_ignores_a_status_key_defense_in_depth`).

════════════════════════════════════════
4. AUTHORIZATION AUDIT
════════════════════════════════════════

Every list/detail/create/update/action view was checked for: login
requirement (`LoginRequiredMiddleware`, project-wide, allowlisted only for
auth pages/healthz/`/admin/`), capability requirement
(`CapabilityRequiredMixin` / `@require_capability`), queryset scoping
(`Model.objects.for_user(user)` + `assert_scoped`), object resolution
(`get_object_or_404(scoped_qs, pk=...)` or the equivalent `_get_<x>` helper —
**zero** instances of an unscoped `Model.objects.get(pk=...)` on a
user-controlled id found project-wide), POST-only mutation
(`@require_POST` or internal method-gating), and GET side effects (only
`notifications:open` — reviewed, see §16). Every `dispatch()` override was
read to confirm it always falls through to `super().dispatch()` before
returning anything — the one exception was Finding #1, fixed.

════════════════════════════════════════
5. IDOR AUDIT
════════════════════════════════════════

Qistas has two authorization shapes, and the IDOR test needed differs by
shape:

- **All-staff-visible domains** (clients, cases, hearings, courts, tasks,
  deadlines, documents, contracts — ADR-0008): every authenticated staff
  member with the domain's `*.view` capability may see every row. "IDOR" here
  means capability-gate bypass (no `X.view` → must 403) and URL-tampering on a
  **nonexistent** pk (→ 404, never 500) — both already covered exhaustively by
  each phase's own permission-matrix tests, re-verified passing this phase.
- **Genuinely siloed domains**: `notifications` (strictly per-recipient —
  `Notification.objects.for_user(user)` returns `recipient=user` rows only,
  **404** on any other pk; exhaustively tested in Phase 11, re-verified
  passing) and `finance` (capability-gated, not row-siloed — a paralegal has
  **zero** access, not "sees fewer invoices"). A new project-wide regression
  file, `tests/test_capability_boundary_sweep.py`, exercises **every** finance
  GET/POST URL, every financial report (page + CSV), the dashboard's
  financial-overview context, the agenda's calendar events, and
  `invoice_overdue` notification generation against a paralegal in one place
  — plus a positive control (an office manager can reach all of them). This
  is where Finding #1 was actually caught.

`cases.view_confidential` gating (`CaseConfidentialUpdateView`) was checked
for the same `dispatch()`-ordering bug as Finding #1 — confirmed clean (its
`dispatch()` always falls through to `super().dispatch()`).

Minor accepted item: `cases.case_lawyer_remove` fetches the target `User`
unscoped (`get_object_or_404(User, pk=user_pk)`) before checking they're
actually linked to the case — a `cases.manage` holder can distinguish
"user id exists" from "doesn't" via 404 vs. a no-op success message. Low
severity (internal staff app, requires `cases.manage`, no client-facing data)
— reviewed, left as-is.

════════════════════════════════════════
6. FINANCE INTEGRITY AUDIT
════════════════════════════════════════

Re-derived from `finance/services.py`, not assumed from ADR-0032's own
description:

- Every money-mutating function is `@transaction.atomic`.
- Every function that must serialize against a concurrent write takes
  `Invoice.objects.select_for_update()` on the invoice row **before** reading
  the balance it validates against: `record_payment` (locks, reads
  `outstanding = credited_total - amount_paid` under the lock, rejects
  `amount > outstanding`, writes via `F("amount_paid") + amount`, refreshes),
  `reverse_payment` (locks the invoice via `payment.invoice_id` — correctly
  serializes reversals of the *same* payment because they all lock the same
  invoice row, not the payment row), `issue_credit_note` (locks, validates
  `already + amount <= invoice.total`).
- DB `CheckConstraint invoice_no_overpayment: amount_paid <= total` is a real
  backstop (confirmed present in `Meta.constraints`, not just documented).
- `Decimal` end to end via `core.money.quantize` (`ROUND_HALF_UP`, 2dp); **no
  float arithmetic found anywhere** in the codebase (grepped).
- Invoice numbering (`invoice_number`, assigned at issue) and immutability
  (no code path mutates a line item or monetary field of an issued invoice —
  `_require_draft` guards every mutator) re-confirmed by reading every caller.
- A theoretical edge case was traced and found non-exploitable: a fully-paid
  invoice later fully credited (`issue_credit_note`) flips to `CANCELLED`
  while `amount_paid` stays at its paid value — `credited_total - amount_paid`
  can go negative, but the DB constraint only guards `amount_paid <= total`
  (still holds: `amount_paid == total`), and every list/report/dashboard
  selector scopes to `.open()` (UNPAID/PARTIALLY_PAID), so a cancelled
  invoice's figures never surface. Not a security issue; not changed
  (inventing a new reconciliation workflow is out of scope for a hardening
  pass).

Real concurrency (`select_for_update` under genuine contention) remains
verifiable only on PostgreSQL — see §18. The logic was re-read line-by-line
this phase and is correct; SQLite's sequential-guard test
(`test_payments.py`) covers the non-concurrent path.

════════════════════════════════════════
7. MIXED CURRENCY
════════════════════════════════════════

Every aggregation point was re-checked: `finance.selectors.
_invoice_totals_by_currency`, `firm_financials` (dashboard), all five
financial report builders (`revenue`/`payments`/`outstanding`/`expenses`/
`case-financials`), and `Invoice.objects.with_balances()`. All group by
currency and never sum across currencies — no new aggregation point was added
this phase, and no regression was found in the existing ones (re-read the
code directly rather than trusting the docstrings/tests).

════════════════════════════════════════
8. DOCUMENT SECURITY AUDIT
════════════════════════════════════════

- **Private storage:** `documents.storage.PrivateFileSystemStorage.url()`
  raises; `STORAGES["documents"]` is a separate entry, never the default,
  never mapped by WhiteNoise (`WHITENOISE_ROOT` unset — confirmed by grep).
  `config/urls.py` has **no** `static(MEDIA_URL, ...)` route — `/media/...`
  is a genuine 404 in every settings module (dev and prod), not merely a
  documented claim.
- **Direct-access attempt:** `documents/tests/test_views.py::
  test_no_public_media_url_for_documents` (existing, re-run this phase) GETs
  both `/media/documents/<real stored path>` and `/media/<real stored path>`
  for an actual uploaded file and asserts 404 — a live, executed proof, not a
  settings inspection.
- **Download boundary:** `document_download` is `@require_GET` +
  `@require_capability(documents.view)` + object-scoped
  (`Document.objects.for_user(user).alive()`) + `get_object_or_404` + audited
  (`record_download` after a successful file open, not before — a missing
  blob never gets logged as a phantom download) + `X-Content-Type-Options:
  nosniff`.
- **Filename handling:** sanitized on both ends — `_safe_original_name`
  (upload) and `Document.download_filename` (download) both strip CR/LF/
  quotes/backslashes and any path segment, capped at 255 chars — no
  `Content-Disposition` header injection, no path traversal via a crafted
  original filename.
- **Storage path:** `document_upload_path` = `<year>/<month>/<uuid4hex>
  <canonical-ext>` — no user-controlled path segment; the extension is the
  validator's canonical one, never the client's filename.
- **Magic-byte / MIME validation:** unchanged from Phase 6 — curated
  signature allowlist, client `Content-Type` ignored, extension must agree
  with the detected family, sha256 streamed in one pass.
- **Audit:** `DOCUMENT_DOWNLOADED` logged with metadata only, never file
  bytes (unchanged).

No document-security defect found.

════════════════════════════════════════
9. AUDIT INTEGRITY REVIEW
════════════════════════════════════════

- `audit.models._AppendOnlyQuerySet` raises `PermissionError` on
  `.update()`/`.delete()`; `AuditLog.delete()` itself also raises.
  `audit.admin.AuditLogAdmin` denies `add`/`change`/`delete` unconditionally
  — re-confirmed by reading the admin class, not assumed.
- django-auditlog's own `LogEntry` admin (`auditlog.admin.LogEntryAdmin`, a
  third-party class) has a delete path gated by the real Django permission
  `auditlog.delete_logentry` — traced into the library source
  (`.venv/Lib/site-packages/auditlog/admin.py`) to confirm this is reachable
  only via `/admin/`, which requires `is_staff=True`. Qistas never grants
  `is_staff` to a regular role (`accounts.models` — only `create_superuser`
  sets it); a role account created the normal way has `is_staff=False`.
  So in practice only a superuser (who already has unrestricted DB access)
  could reach that path — not a Phase 12 finding, matches architecture.md §5
  by design.
- **Sensitive data never logged:** cross-checked `core.sensitive.
  SENSITIVE_FIELDS` against every domain's `AuditLog` `changes=` call sites —
  no `national_id`, `legal_notes`/`internal_notes`, document bytes, or
  notification bodies appear in any audit changes dict; finance events log
  metadata (numbers, statuses, field names) never full monetary bodies.
- **Coverage:** every domain mutation (`clients`, `cases`, `hearings`,
  `tasks`, `documents`, `contracts`, `finance`) emits an `AuditLog` event via
  its `services.py`; `notifications` deliberately emits none (spec §46 does
  not list notifications; an inbox row is not a domain record — ADR-0035).
  No missing coverage found in any later phase.

════════════════════════════════════════
10. NOTIFICATION SECURITY REVIEW
════════════════════════════════════════

Re-read `notifications/{models,services,generation,views,selectors}.py` fresh
(not trusting Phase 11's self-review):

- **Recipient authorization:** `Notification.objects.for_user(user)` filters
  strictly to `recipient=user`; every view/action goes through it;
  `get_object_or_404` → **404 on tamper** (confirmed still true — Phase 11's
  tests re-run and pass, plus this phase's new
  `test_paralegal_receives_no_invoice_overdue_notification` adds one more
  angle at the generation layer).
- **Dedupe:** `UniqueConstraint(recipient, dedupe_key)` + the
  `filter(dedupe_key__in=…)` + `bulk_create(ignore_conflicts=True)` pattern —
  re-read, no race that could duplicate or misattribute a notification.
- **Stored URLs:** every notification's `url` targets a domain detail view
  that re-enforces its own capability + scope — following a notification link
  is never an authorization bypass (re-verified for all 5 categories).
- **Finance isolation:** `scan_overdue_invoices` draws recipients only from
  office-manager + finance-clerk, intersected with `users_with_capability(
  finance.view)` — a paralegal is excluded at both the recipient-selection and
  the capability-intersection layer, independently. New regression:
  `tests/test_capability_boundary_sweep.py::
  test_paralegal_receives_no_invoice_overdue_notification`.
- **No sensitive values in bodies:** confirmed no notification body contains
  an amount/balance — only reference numbers, names, and dates.

No notification-security defect found.

════════════════════════════════════════
11. REPORT SECURITY REVIEW
════════════════════════════════════════

`ReportView.get` checks `can(user, report.capability)` before any query or
file generation, for both the HTML page and `?format=csv` — re-verified by
reading the view, not the docstring. New regression:
`tests/test_capability_boundary_sweep.py::
test_paralegal_403_on_every_financial_report` (all five financial reports,
page **and** CSV, in one place, alongside the finance-URL sweep — so a future
regression in either surface is caught by the same file). Spreadsheet
injection guard (`csv_safe`), no stored/temp files (CSV is streamed straight
to the response, never written to disk), audit-metadata-only export logging —
all re-confirmed unchanged from Phase 10.

════════════════════════════════════════
12. DASHBOARD SECURITY REVIEW
════════════════════════════════════════

`dashboard.selectors.build_dashboard` reads `capabilities_for(user)` once and
only computes a widget's data if the capability is held —
`financial_overview` and every finance-touching block is gated on
`Capability.FINANCE_VIEW` **in the query**, not just hidden in the template
(re-read `dashboard/selectors.py` directly). New regression:
`tests/test_capability_boundary_sweep.py::
test_paralegal_dashboard_shows_no_financial_overview` asserts
`financial_overview["visible"] is False`, `show_finance is False`, **and**
that the page body contains no invoice number for a paralegal — a backend
*and* rendered-HTML check in the same test, not backend-only.

════════════════════════════════════════
13. PERFORMANCE / N+1 REVIEW
════════════════════════════════════════

All 10 existing query-count regression tests across dashboard, reports,
notifications, contracts, and finance were re-run and pass unchanged. Both
Phase 12 fixes are pure control-flow changes (no new queries, no removed
`select_related`/`prefetch_related`) — confirmed by inspection, no new N+1
introduced. No new performance regression test was needed since no query
pattern changed.

════════════════════════════════════════
14. DATABASE INTEGRITY REVIEW
════════════════════════════════════════

Grepped every `on_delete=models.CASCADE` in the project (excluding the test
app) and confirmed each is within an aggregate root per ADR-0022:
`CaseConfidential`/`CaseLawyer`/`CaseParty`/`CaseNote`/`CaseEvent` → `Case`;
`InvoiceLineItem` → `Invoice`; `Notification` → its own `recipient` User.
**Never** `CASCADE` into `Case`, `Hearing`, `Invoice`, `Payment`, `Document`,
`Contract`, or `AuditLog` — confirmed, no violation found. Money
`CheckConstraint`s spot-checked (`amount_paid <= total`, positive-amount
guards on `Payment`/`PaymentReversal`/`CreditNote`/`Expense`) — all present
as declared. No new constraint added or needed — nothing found that exists
only in Python and should also be a DB constraint.

════════════════════════════════════════
15. TRANSACTION / CONCURRENCY REVIEW
════════════════════════════════════════

Every multi-write business operation confirmed `@transaction.atomic`: invoice
issuance, payment creation/reversal, credit notes, contract/case/client/
invoice/payment numbering (`core.numbering.next_number` under
`select_for_update` on the sequence row), fee-agreement status changes,
document metadata updates, expense mutations. Notification generation
(`bulk_notify`) is not itself wrapped in one atomic block spanning the whole
scan — each `bulk_create` is its own implicit transaction, which is correct
here: notifications are independent, idempotent, additive rows with a unique
constraint as the race backstop, not a multi-row invariant that needs
all-or-nothing semantics. No race condition found in any reviewed path beyond
what ADR-0032's `select_for_update` design already covers.

════════════════════════════════════════
16. AUTHENTICATION / SESSION SECURITY REVIEW
════════════════════════════════════════

- `accounts.views.LoginView` subclasses Django's built-in `LoginView`
  unmodified in its authentication path — session-key rotation on login is
  Django's default (`login()` calls `cycle_key()`), not overridden here, so
  no session-fixation risk.
- `PasswordChangeView` uses Django's default `form_valid` →
  `update_session_auth_hash` (keeps the current session alive, invalidates
  the auth hash for any other session using the old password) — unmodified.
- `PasswordResetView`/`…DoneView`/`…ConfirmView`/`…CompleteView` are Django's
  built-in, enumeration-safe flow — unmodified (no custom `form_valid` that
  could leak whether an email exists).
- **Lockout:** django-axes locks by **username only** (never IP — the office
  shares one NAT IP; IP lockout would be a self-DoS), a deliberate, documented
  ADR-0026 decision. `axes.W006` ("add ip_address to
  AXES_LOCKOUT_PARAMETERS") is silenced — traced into
  `axes/checks.py` to confirm this is exactly the warning that decision
  intentionally overrides, not an unrelated one silenced by habit.
- **MFA:** `MFAEnforcementMiddleware.process_view` blocks every
  non-allowlisted view for a user with a confirmed authenticator who hasn't
  completed the OTP step this session — re-read the allowlist
  (`ALLOWED_VIEW_NAMES`) and confirmed it is narrow (setup/activate/manage/
  disable/token/logout/healthz only).
- `mfa_disable` has no `@require_http_methods` decorator but internally gates
  the actual device deletion to `request.method == "POST"` — a GET only
  renders the confirm form. Functionally safe (no GET-triggered mutation);
  left as-is (adding the decorator would be a pure style change with no
  behavior difference).
- **Cookies:** `SESSION_COOKIE_HTTPONLY = True`, `CSRF_COOKIE_HTTPONLY =
  True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_SAMESITE = "Lax"` —
  confirmed present in `config/settings/base.py`; `SESSION_COOKIE_SECURE` /
  `CSRF_COOKIE_SECURE` are `True` in `config/settings/prod.py` (correctly
  `False`-by-Django-default under `dev`/`test`, where there is no HTTPS).
- **Idle timeout:** `IdleTimeoutMiddleware` logs a session out after
  `IDLE_TIMEOUT_SECONDS` (default 30 min) of inactivity — re-read, correct.

No authentication/session defect found.

════════════════════════════════════════
17. DEPLOYMENT SECURITY REVIEW
════════════════════════════════════════

`manage.py check --deploy` was run against **`config.settings.prod`** with a
genuinely random 86-character `DJANGO_SECRET_KEY`, a real
`DJANGO_ALLOWED_HOSTS`, and a real `DJANGO_CSRF_TRUSTED_ORIGINS` (a SQLite
`DATABASE_URL` was substituted for `DATABASE_URL` — the deploy check does not
touch the database engine, so this is a valid way to run it without
PostgreSQL/Docker):

```
System check identified no issues (1 silenced).
```

The 1 silenced check is `axes.W006` (§16, intentional). This is a genuine
upgrade over every prior phase's "test-settings only, PG needed" deferral —
the actual production settings module is now empirically verified, not
merely inspected. Confirmed present in `prod.py`: `DEBUG = False`,
`SECRET_KEY` from env with no insecure default (fails loudly if unset),
`ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` from env, `SECURE_SSL_REDIRECT = True`,
`SECURE_PROXY_SSL_HEADER`, `SECURE_HSTS_SECONDS` (1 year) +
`INCLUDE_SUBDOMAINS` + `PRELOAD`, `SESSION_COOKIE_SECURE = True`,
`CSRF_COOKIE_SECURE = True`, `SECURE_REFERRER_POLICY = "same-origin"`,
`SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"`. `X_FRAME_OPTIONS =
"DENY"` and `SECURE_CONTENT_TYPE_NOSNIFF = True` are set in `base.py` (apply
in every environment). MIDDLEWARE ordering re-checked against Django's
documented requirements (Session → Locale → Common → CSRF → Auth → OTP) —
correct.

`config.settings.test` still shows the same 5 warnings it always has
(HSTS/SSL-redirect/weak-secret/insecure-cookies) — confirmed these are
test-settings-only, not a production gap, by the prod-settings run above.

════════════════════════════════════════
18. DEPENDENCY AUDIT
════════════════════════════════════════

`pip-audit`: **no known vulnerabilities** (re-run this phase, same result as
every prior phase). Every dependency in `pyproject.toml` is pinned to an
exact version (`Django==5.2.17`, `psycopg[binary]==3.2.13`,
`django-environ==0.14.0`, `whitenoise==6.12.0`, `django-axes==8.3.1`,
`django-otp==1.7.3`, `qrcode==8.2`, `django-auditlog==3.4.1`,
`django-htmx==1.29.0`; dev: `pytest==9.0.3` — already pinned above a known
CVE per its own inline comment, `pytest-django==4.14.0`,
`pytest-cov==7.1.0`, `factory-boy==3.3.3`, `Faker==37.8.0`, `ruff==0.14.2`,
`django-debug-toolbar==6.0.0`, `pip-audit==2.9.0`). **No upgrade made** — none
was needed (per the instruction to upgrade only for a concrete
security/compatibility reason).

════════════════════════════════════════
19. POSTGRESQL VERIFICATION
════════════════════════════════════════

**Still DEFERRED.** Re-attempted this phase: `docker info` fails (no daemon
running), `psql` is not on `PATH`, and `python -c "import psycopg"` raises
`ModuleNotFoundError` — the same environment blocker as every prior phase
(this machine has no Docker/PostgreSQL access; RAM + network constraints
documented since Phase 1). What *was* achieved without PostgreSQL this phase:
`manage.py check --deploy` against real prod settings (§17, doesn't need a
live DB) — a genuine, not partial, verification win.

Unverified: the full suite on PostgreSQL 16 (expect ~755 pass, 0 skipped); the
4 `@pytest.mark.postgres` tests, most importantly
`test_concurrent_payments_cannot_overpay` (the one that actually exercises
`select_for_update` under real row-level locking — the SQLite-only run
substitutes a sequential guard test, and this phase re-derived the locking
logic from the code and found it correct, but genuine concurrent contention is
untestable without PostgreSQL); the trigram-index migrations (guarded,
PG-only, no-op on SQLite).

════════════════════════════════════════
20. DOCKER VERIFICATION
════════════════════════════════════════

**Still DEFERRED**, same blocker as §19 (`docker info` fails — no daemon).
`docker compose build && docker compose run --rm web pytest` and a full-stack
`docker compose up` smoke test were not run. `compilemessages` (needs GNU
gettext, Docker-only on this Windows host) was not run — harmless, the app
ships `ar` only and all source strings are already Arabic.

Exact commands for a capable machine / CI:
```
docker compose build && docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest                                  # expect ~755 pass, 0 skipped
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
docker compose up -d && curl -si localhost:8000/                    # -> 302 /accounts/login/
```

════════════════════════════════════════
21. TEST RESULTS
════════════════════════════════════════

- **755 pass / 0 fail / 4 skipped** (`@pytest.mark.postgres`) on SQLite —
  **+14 Phase 12 tests**:
  - `tests/test_capability_boundary_sweep.py` (8): every finance GET/POST URL
    403s a paralegal (with an office-manager positive control), every
    financial report page + CSV 403s a paralegal, the dashboard shows no
    financial overview + no invoice number in the rendered HTML for a
    paralegal, the agenda has no invoice events for a paralegal, a paralegal
    receives zero `invoice_overdue` notifications, and the specific
    Finding #1 regression (paralegal 403s on an issued invoice's edit URL).
  - `finance/tests/test_invoices.py` (3): issued-invoice edit POST also
    redirects for an authorized user; a draft invoice's edit view still
    renders 200; a paralegal 403s identically on both a draft and an issued
    invoice's edit URL.
  - `clients/tests/test_views.py` (2): a smuggled `status=archived` in an
    update POST is silently ignored (the real field edit still applies, the
    status doesn't change); the edit form never renders a `status` field.
  - `clients/tests/test_audit.py` (1): `update_client` ignores a `status` key
    even when called directly (service-layer defense-in-depth), and the audit
    diff never contains `"status"`.
- Full Phase 1–11 regression suite: all pre-existing tests re-run and pass —
  **no regression introduced**.
- `ruff check .` — clean. `ruff format --check .` — clean (308 files).
- `pip-audit` — no known vulnerabilities.
- `manage.py makemigrations --check --dry-run` — no changes (no model
  touched this phase).
- `manage.py check` — no issues (1 silenced).
- `manage.py check --deploy` — `config.settings.test`: 5 warnings, confirmed
  test-settings-only (§17). `config.settings.prod` with real values: **0
  warnings, 1 silenced.**

════════════════════════════════════════
22. REMAINING KNOWN LIMITATIONS
════════════════════════════════════════

- `notifications:open` marks a notification read on `GET`, by design (§16 of
  the Phase 12 brief explicitly asked about this) — a forgeable
  cross-site GET, but the only effect is flipping the victim's own `read_at`
  on their own row; no data exposure, no destructive action. First documented
  in Phase 11 (ADR-0035 §4); re-reviewed this phase and accepted as-is —
  fixing it would mean a POST-based "open" flow, a UX change out of proportion
  to the severity.
- `cases.case_lawyer_remove` fetches the target `User` unscoped before the
  case-link check — a minor existence-oracle for a `cases.manage` holder, no
  client-facing exposure (see §5).
- A fully-paid invoice later fully credited can show a negative
  `credited_total - amount_paid` internally, though it never surfaces in any
  UI/report because closed invoices are excluded from every "open" selector
  (see §6) — accepted, not changed (would require inventing a reconciliation
  workflow, out of scope for hardening).

════════════════════════════════════════
23. DEFERRED ITEMS
════════════════════════════════════════

- PostgreSQL 16 full suite + the 4 `@pytest.mark.postgres` tests (§19).
- Docker Compose full-stack smoke test (§20).
- `compilemessages` (Docker-only; harmless).
- Server-side PDF export remains deferred by design since Phase 10
  (ADR-0034 §7) — unrelated to this phase, not re-opened.

════════════════════════════════════════
24. BRANCH
════════════════════════════════════════

phase/12-hardening

════════════════════════════════════════
25. COMMIT
════════════════════════════════════════

phase(12): complete hardening

════════════════════════════════════════
26. PARENT COMMIT
════════════════════════════════════════

6a76894 (Phase 11 merge, PR #10, `master` HEAD at branch creation)

════════════════════════════════════════
WORKING-TREE STATUS
════════════════════════════════════════

Clean after the final commit; pushed to `origin/phase/12-hardening`;
**not merged** — awaiting explicit "APPROVE PHASE 12".
