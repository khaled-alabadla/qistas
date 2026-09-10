━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:        8 — Finance
Status:       COMPLETE (technical) — PostgreSQL / Docker verification DEFERRED
              (same environment blocker as Phases 1–7; every other DoD item met)
Branch:       phase/8-finance — based on master @ 7908beb (Phase 7 merge, PR #6)
Design:       docs/adr/0032-finance.md (Accepted) — building on ADR-0011, 0012, 0013

════════════════════════════════════════
1. IMPLEMENTATION SUMMARY  (spec §37–42, §21, §97, §98, §82 Phase 8)
════════════════════════════════════════

New `finance` app — one app, six models, standard layering (models / selectors /
services / thin views / forms). Every amount is `Decimal`; every stored monetary
result goes through `core.money.quantize` (2 dp, `ROUND_HALF_UP`); all arithmetic
is server-side in `finance.services`. No finance row is ever hard-deleted.

── MODELS ──────────────────────────────

**FeeAgreement** ("رسوم القضايا" = the agreed legal fee, NOT an expense — ADR-0013)
`reference` `FA-YYYY-NNNN` · FK `case` **PROTECT** · `fee_type` (fixed / hourly /
contingency / retainer) with the matching money field validated in `clean()` +
`CheckConstraint` (`fixed_amount` / `hourly_rate` / `contingency_percent` 0–100) ·
`currency` · `status` (draft → active → completed / cancelled; guarded transitions,
`cancelled` terminal) · dates · `description` / `notes`. **No delete**
(`default_permissions = add/change/view`).

**Invoice** — stored totals, frozen at issue (ADR-0011, 0012)
`invoice_number` `INV-YYYY-NNNN` **assigned at issue** (not draft; nullable,
unique, gaps OK) · FK `client` **PROTECT** / `case` **SET_NULL** / `fee_agreement`
**SET_NULL** · `status` (draft / unpaid / partially_paid / paid / cancelled — the
three payment states derived by the service from `amount_paid`, never a form) ·
`issue_date` / `due_date` / `currency` · **inputs** `discount` (≥ 0) + `tax_rate`
(0–100) · **server-computed snapshots** `subtotal` = Σ line totals,
`taxable` = `max(subtotal − discount, 0)`,
`tax_amount` = `quantize(taxable × tax_rate/100)`, `total` = `taxable +
tax_amount` (never negative; `issue_invoice` rejects `discount > subtotal`),
`amount_paid` (maintained only by the service under a row lock).
`CheckConstraint`s: every money field ≥ 0, `tax_rate` 0–100, **`amount_paid ≤
total`** (the DB backstop for the overpayment guard). (No `discount ≤ subtotal`
DB constraint — a discount set before line items would trip it; it is enforced at
issue instead, buglog bug-084.) **No delete**; a **draft**
may be cancelled directly, an **issued** invoice only by a full-value credit note.
`is_overdue` / `days_overdue` are **computed, never stored** (ADR-0006) — overdue
flips back the moment the invoice is paid, so it is a property, not a lifecycle
status (contrast a contract's `expired`).

**InvoiceLineItem** — FK `invoice` **CASCADE** (aggregate-root child). `description`
· `quantity` (> 0) · `unit_price` (≥ 0) · `line_total` = `quantize(qty × price)`
(stored, frozen). Added / removed only while `draft`, through dedicated service
calls (the `CaseParty` add/remove idiom — **no formset**); each re-runs
`recalculate_invoice`.

**Payment** — immutable, overpayment-safe (§40, ADR-0012)
`reference` `PMT-YYYY-NNNN` · FK `invoice` **PROTECT** · `amount` (> 0) ·
`paid_on` · `method` (cash / bank_transfer / cheque / card / other) ·
`external_reference` / `note`. **`default_permissions = add/view`** — no change,
no delete; admin add/change/delete all off.

**PaymentReversal** — FK `payment` **PROTECT** · `amount` (> 0, Σ ≤ payment.amount)
· `reason` · `reversed_on`. `add/view` only.

**CreditNote** — FK `invoice` **PROTECT** · `credit_number` `CN-YYYY-NNNN` ·
`amount` (> 0, Σ ≤ invoice.total) · `reason` · `issued_on`. `add/view` only.
Only against a non-draft, non-cancelled invoice; a full-value note flips the
invoice to `cancelled`.

**Expense** — money out, standalone (ADR-0013, §41)
`reference` `EXP-YYYY-NNNN` · `description` · `amount` (> 0) · `currency` ·
`category` (court_fees / government_fees / expert_fees / travel / office /
translation / other) · `spent_on` · FK `case` **SET_NULL** / `client`
**SET_NULL** (§41 — Office / Case / Client) · `note`. **Editable**;
**soft-delete** via `deleted_at` + `deleted_by` (retained + audited, never
hard-deleted). **Never added to an invoice total or a fee agreement.**

── SERVICES / SELECTORS ────────────────

`finance.services` — every write in `transaction.atomic`, all money math here:
`create_fee_agreement` / `update_fee_agreement` / `change_fee_agreement_status` ·
`create_invoice` / `update_invoice` (draft only — refuses a non-draft) /
`add_line_item` / `remove_line_item` / `recalculate_invoice` / `issue_invoice`
(**row-locked**; allocates the number, checks `discount ≤ subtotal` + `total > 0`,
re-checks status under the lock so a double-submit cannot issue twice) /
`cancel_invoice` (draft only) · **`record_payment`** — the overpayment guard:
`select_for_update`
on the invoice row, reads `credited_total − amount_paid` under the lock,
`amount > outstanding` → `ValidationError`, `F("amount_paid") + amount` atomic
increment, status recomputed · `reverse_payment` · `issue_credit_note` · Expense
CRUD + `retire_expense`.

`finance.selectors` — `fee_agreement_list` / `invoice_list` / `payment_list` /
`expense_list` (search + filters + pagination; default branch hides
closed/cancelled/retired — the `else` branch, cf. bug-055) · `invoice_detail_queryset`
(prefetches line items / payments+reversals / credit notes — fixed query count) ·
`case_*` / `client_*` reads · `client_financials` / `case_financials`
(إجمالي الفواتير / المدفوع / المتبقي — a **per-currency**, **credit-note-aware**
breakdown over **issued** invoices; different currencies are never summed) ·
`outstanding_invoices` (landing; NULL due dates sort last) · `calendar_items`
(invoice due dates for the
agenda — **re-checks `finance.view`** since the agenda is all-staff).
`Invoice.objects.with_balances()` annotates `_credited_sum` so `outstanding` /
`credited_total` need no per-row query on lists.

── UI ─────────────────────────────────

`finance` app pages: fee-agreement list / detail / create / edit / status;
invoice list / detail (line-item add/remove, issue, cancel, record payment,
issue credit note — all inline on the detail page) / draft create / draft edit;
payment list / detail / reverse; expense list / detail / create / edit / retire.
`المالية` nav section (الفواتير / المدفوعات / المصروفات / رسوم القضايا) live,
gated on `finance.view`. `core:landing` "المبالغ المستحقة" widget. Case workspace
gains a real **المالية** tab (fee agreement + invoices + payments + expenses +
summary). Client profile: real **ملخص مالي** + الفواتير + المدفوعات cards; only
`القضايا` remains in the client `disabled_tabs` now. Arabic-first RTL,
`Decimal` money via a shared `finance/_money.html` partial, `<bdi>` for figures,
existing components — no new frontend anything. `seed_demo_finance` command.

── PERMISSIONS / AUDIT ────────────────

- **`finance.view`** — office_manager, finance_clerk, lawyer, admin_clerk.
  **paralegal has NO finance access** (§12 — "limited access to assigned work";
  the first domain that is not all-staff, §98). List + detail.
- **`finance.manage`** — office_manager + finance_clerk **only**. Every mutation.
- `sync_roles` maps the model codenames — **no `delete` codename anywhere in
  finance**; Payment / PaymentReversal / CreditNote have no `change` either.
- `audit.AuditAction` +13 members (`FEE_AGREEMENT_*`, `INVOICE_*`, `PAYMENT_*`,
  `CREDIT_NOTE_ISSUED`, `EXPENSE_*`). `cases.CaseEventType` +4
  (`FEE_AGREEMENT_ADDED`, `INVOICE_ISSUED`, `PAYMENT_RECORDED`,
  `CREDIT_NOTE_ISSUED` — case-linked milestones only; migration `cases/0008`).
- Every `log_event` carries **metadata only** (references, numbers, amounts,
  status, changed field names) — `description` / `notes` / `reason` bodies are
  never in `changes` (ADR-0009). django-auditlog registers the 3 editable models.

════════════════════════════════════════
2. MIGRATIONS
════════════════════════════════════════

- `finance/0001_initial` — 6 models + indexes + CheckConstraints.
- `finance/0002_finance_search_indexes` — trigram GIN (guarded, PostgreSQL-only;
  `*_TRGM_COLUMNS == *_SEARCH_FIELDS`, regression-tested).
- `cases/0008_alter_caseevent_event_type` — +4 `CaseEventType` choices.
- (`audit` needs no migration — `AuditLog.action` is a plain `CharField`.)

`makemigrations --check` — clean.

════════════════════════════════════════
3. TESTS
════════════════════════════════════════

**529 pass / 0 fail / 4 skipped** (SQLite) — was 439/3; **+90 finance tests**,
+1 `@pytest.mark.postgres` skip (the concurrent-overpayment test — `select_for_update`
is a no-op on SQLite; a sequential-guard test covers the SQLite path).

`finance/tests/`: `test_models` (Decimal, `quantize` half-up, every
CheckConstraint, `clean()`, uniqueness, CASCADE / PROTECT, no-delete permissions,
trigram columns) · `test_fee_agreements` (create / reference / metadata-only audit
/ guarded status transitions / no-edit-when-closed / views / authz) ·
`test_invoices` (server-side totals · **forged totals/number/status in POST
ignored** · discount-over-subtotal zeroes total + blocks issue · issuance +
number uniqueness · **issued immutability** (service + view) · draft cancel ·
credit notes: full = void, partial = reduce outstanding, cap at total, issued-only
· line add/remove via view · foreign-line 404 · URL-tampering 404 ·
**query-count-is-flat N+1 guard**) · `test_payments` (partial→exact status walk ·
multiple payments · **overpayment rejected & nothing written** · after-partial ·
zero/negative · can't-pay draft/cancelled · **@postgres concurrent-overpayment**
(5 of 10 × 20 succeed on a 100 invoice; `amount_paid ≤ total` held) · sequential
guard on SQLite · reversal reduces `amount_paid` + status · reversal cap · view
authz / post-only / overpay-shows-error-not-500 · detail URL-tampering 404) ·
`test_expenses` (reference / audit · **expense never inflates invoice totals** ·
negative rejected · update / soft-delete idempotent / no-edit-retired · views /
authz) · `test_permissions` (capability matrix incl. **paralegal = no access** ·
paralegal can't reach any finance page · lawyer view-but-not-mutate · anonymous →
login · mutations POST-only · prefill ignores out-of-scope ids · expense
mass-assignment · `sync_roles --check` · **agenda calendar excludes finance for a
non-viewer**) · `test_smoke` (16-URL HTTP smoke + `seed_demo_finance`).

Existing 439 Phase 1–7 tests — unchanged and still green.

════════════════════════════════════════
4. LINT / FORMAT / SECURITY / DJANGO CHECKS
════════════════════════════════════════

- `ruff check .` — **clean**
- `ruff format --check .` — **clean**
- `pip-audit` — **no known vulnerabilities** (only the local editable `qistas`
  package skipped)
- `manage.py makemigrations --check --dry-run` — **no changes**
- `manage.py check` (test settings) — **no issues**
- `manage.py check --deploy` — 5 warnings (`security.W004/W008/W009/W012/W016`),
  **all test-settings-only** — `config/settings/prod.py` sets HSTS,
  `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` and takes
  `DJANGO_SECRET_KEY` from the environment. A real prod-settings run needs the
  env + PostgreSQL (see §8).

════════════════════════════════════════
5. CODE REVIEW
════════════════════════════════════════

`/code-review high` (multi-agent) — 7 findings, **all fixed**, +4 regression tests:

1. **`client_financials` / `case_financials` summed different currencies into one
   figure.** → Rewritten to a **per-currency breakdown** (`by_currency` /
   `expenses_by_currency`); the shared `finance/_summary.html` partial renders
   one block per currency. New test.
2. **The same summaries ignored credit notes**, contradicting the credit-aware
   `inv.outstanding` shown beside them. → Now subtract Σ credit notes per
   currency (aggregated in a separate query so `total` / `amount_paid` don't fan
   out over the credit-note join). New test.
3. **`issue_invoice` took no row lock** → a double-submit could issue twice,
   burning a number and doubling the audit + case events. → Now
   `Invoice.objects.select_for_update().get(...)` + re-check status under the
   lock (same pattern as `record_payment`). New `test_cannot_issue_an_already_
   issued_invoice`.
4. **`invoice_issue` view discarded `form.is_valid()`** → a malformed `issue_date`
   silently became today. → Now shows an error and bounces.
5. **`update_invoice` could not clear `discount` / `tax_rate`** — a blank field
   was skipped, not zeroed. → New `_money_inputs()` helper: a present-but-blank
   input means "clear" → `ZERO`. New `test_clearing_discount_via_update_zeroes_it`.
6. **An invoice could pair a fee agreement from a different case.** → New
   `_check_invoice_links()` rejects the mismatch in `create_invoice` /
   `update_invoice`. New `test_invoice_rejects_fee_agreement_from_a_different_case`.
7. **`outstanding_invoices` ordered by `due_date` with no NULL handling** →
   undated open invoices could be hidden on the landing widget on PostgreSQL. →
   `order_by(F("due_date").asc(nulls_last=True), "-created_at")` (the
   `my_open_tasks` pattern).

════════════════════════════════════════
6. SECURITY REVIEW
════════════════════════════════════════

Self review — **PASS** (no Critical/High).

- **Authorization** — `CapabilityRequiredMixin` (view/manage) on every CBV,
  `@require_capability` + `@require_POST` on every function view. Object access
  through `_scoped_*` helpers (`for_user()` + `assert_scoped` + `get_object_or_404`);
  the `record_payment` / `reverse_payment` / `issue_credit_note` services take an
  id but the **view resolves the scoped object first** for authz, then the
  service re-fetches under `select_for_update` (trusted internal path, ADR-0019).
  Tests: URL-tampering → 404, foreign-line → 404, paralegal → 403 everywhere.
- **Forged totals / balances / numbers** — `create_invoice` / `update_invoice`
  filter POST to `INVOICE_DRAFT_EDITABLE` + `INVOICE_DRAFT_MONEY_INPUTS`
  allowlists; `subtotal` / `tax_amount` / `total` / `amount_paid` / `invoice_number`
  / `status` are never accepted from the client. `recalculate_invoice` is the sole
  writer of the computed fields; references are server-allocated. Regression-tested.
- **Overpayment / race** — `record_payment` holds a `select_for_update` lock on
  the invoice row across the read of the outstanding balance and the write of
  `amount_paid`; `amount_paid ≤ total` `CheckConstraint` is the DB backstop.
  `issue_credit_note` / `reverse_payment` take the same lock, so they serialize
  with payments. `@postgres` test proves 10 concurrent × 20 on a 100 invoice →
  exactly 5 succeed, `amount_paid == total`.
- **Issued-invoice immutability (ADR-0012)** — `_require_draft` in every content
  mutator; `issue_invoice` / `cancel_invoice` reject a non-draft; the edit view
  bounces an issued invoice to detail; admin freezes issued fields + delete off.
- **Sensitive-data leakage** — finance is capability-gated, not all-staff (§98).
  Every all-staff surface that could reach finance data re-checks `finance.view`:
  `calendar_items` (the agenda is all-staff — regression-tested), the case
  workspace `finance` tab, the client-profile finance cards, and
  `case_financials` / `client_financials` (only computed when `can_finance`).
- **Audit** — metadata only; `description` / `notes` / `reason` bodies never in
  `changes` (tested). No financial row is hard-deletable (tested).
- **XSS** — templates auto-escape; no `|safe` / `mark_safe`; money via a
  `floatformat` partial. **CSRF** — token on every form, POST-only mutators.
  **SQLi** — pure ORM; `search()` over hardcoded field tuples; trigram DDL over
  hardcoded column tuples.

════════════════════════════════════════
7. PERFORMANCE / N+1 REVIEW
════════════════════════════════════════

Self review — **PASS**.

- `invoice_list` / `outstanding_invoices` / `case_invoices` / `client_invoices` /
  `calendar_items` use `Invoice.objects.with_balances()` — a
  `Coalesce(Sum("credit_notes__amount"), 0)` annotation — so `outstanding` /
  `credited_total` are read from the row, **not** a per-invoice aggregate.
  `Invoice.total_credited` prefers the annotation, then the prefetch cache, then
  (last resort) one aggregate. New regression test asserts the invoice-list query
  count is **flat** as row count grows (3 → 9 invoices, identical count).
- `Payment.reversed_amount` reads the `_prefetched_objects_cache` when the caller
  prefetched `reversals` (payment lists, invoice detail all do).
- `invoice_detail_queryset` `select_related`s the 4 FKs and `prefetch_related`s
  line items / payments→reversals / credit notes — a fixed query count for any
  invoice.
- All list views paginate (`PAGE_SIZE = 25`).
- `client_financials` / `case_financials` — one `.aggregate()` each (two `Sum`s
  on the invoice table, no join fan-out), computed only for `finance.view` holders.
- **Known pre-existing (not introduced by Phase 8):** the per-request `can()` /
  navigation capability checks issue ~1 `auth_group` query per nav item on every
  page in the app. ADR-0010 defers this whole-app N+1 sweep to Phase 12; the new
  regression test explicitly scopes around it.

════════════════════════════════════════
8. POSTGRESQL / DOCKER STATUS  (DEFERRED — same environment blocker as Phases 1–7)
════════════════════════════════════════

This machine cannot run Docker or PostgreSQL (RAM + network). NOT executed:

1. Full suite on **PostgreSQL 16** (SQLite only here).
2. Trigram / `pg_trgm` migrations on real PG — `core/0002`, `clients/0002`,
   `cases/0003`, `courts/0003`, `tasks/0002`, `documents/0002`, `contracts/0002`,
   **`finance/0002`** (all vendor-guarded → no-op on SQLite).
3. The 4 `@pytest.mark.postgres` tests — including
   **`test_concurrent_payments_cannot_overpay`** (the one that actually exercises
   `select_for_update` row locking; on SQLite `select_for_update` is a no-op and
   the sequential guard test covers that path instead).
4. `docker compose build` + `docker compose run --rm web pytest` full-stack smoke.
5. `compilemessages` (Docker/gettext only; harmless).
6. `manage.py check --deploy` against **prod settings** (needs `DJANGO_SECRET_KEY`
   env + PostgreSQL).

Run on a PG-capable machine / CI:
```
docker compose build && docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest            # expect 533 pass, 0 skipped
docker compose run --rm web python manage.py sync_roles --check
docker compose run --rm web python manage.py seed_demo_finance
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.prod \
  web python manage.py check --deploy
```

════════════════════════════════════════
9. KNOWN LIMITATIONS
════════════════════════════════════════

- **Overdue is a computed flag, not a stored `متأخرة` status.** Spec §39 lists
  `متأخرة` among the statuses; ADR-0032 keeps it computed (ADR-0006) because an
  invoice's overdue-ness flips back the instant it is paid and depends on the
  current date — a cron-flipped status would be wrong half the time. The list
  filter, the landing widget and the badges surface it. Documented in ADR-0032.
- **A discount entered before line items is stored as-is** (no DB `discount ≤
  subtotal` constraint); `recalculate_invoice` never lets `total` go negative
  (`taxable = max(subtotal − discount, 0)`) and `issue_invoice` rejects
  `discount > subtotal`. The normal workflow is create → add lines → set discount.
- **No optimistic-locking token on draft-invoice edits** (architecture §13
  "design intent"). Issued-invoice immutability + the payment row lock cover the
  real concurrency risks; a draft is single-clerk work. Recorded as a possible
  future change.
- Reimbursable-expense-on-invoice, multi-currency conversion, tax-registration
  numbers, a gap-free invoice sequence (ADR-0011), and fee → invoice pre-fill are
  explicit **non-goals for v1**.
- Financial **reports** (revenue / outstanding / expense roll-ups) are Phase 10;
  the operational **dashboard** is Phase 9; **notifications** (invoice overdue) are
  Phase 11. No Phase 9+ functionality was introduced (verified: no `Report*`,
  no dashboard KPIs, no notification models; `grep -rn` for those terms in
  `finance/` is empty).

════════════════════════════════════════
10. FILES
════════════════════════════════════════

New: `finance/` (app — models, services, selectors, forms, views, urls, admin,
audit, apps, 2 migrations, `seed_demo_finance`, 7 test modules + factories),
`core/money.py`, `templates/finance/` (11 templates + 3 partials),
`docs/adr/0032-finance.md`, `docs/PHASE_8_REPORT.md`.

Changed: `core/permissions/capabilities.py`, `accounts/.../sync_roles.py`,
`audit/models.py`, `cases/models.py` + `cases/0008`, `cases/views.py`,
`templates/cases/case_detail.html`, `clients/views.py`,
`templates/clients/client_detail.html`, `agenda/selectors.py`, `core/views.py`,
`templates/core/landing.html`, `core/navigation.py`, `config/settings/base.py`,
`config/urls.py`, `PROJECT_STATUS.md`, `docs/architecture.md`, `docs/adr/README.md`.

════════════════════════════════════════
11. GIT
════════════════════════════════════════

- Branch:        phase/8-finance
- Parent commit: 7908beb  (Merge pull request #6 from …/phase/7-contracts — master)
- Commit:        <filled after `phase(8): complete finance`>
- Working tree:  clean after the commit; local HEAD == origin/phase/8-finance
- **NOT merged.** No changes to master.
