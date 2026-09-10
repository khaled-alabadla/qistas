# ADR-0032 — Finance: fee agreements, invoices, payments, credit notes, expenses

- **Status:** Accepted — 2026-09-10
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0006 (computed states, no cron for derived flags),
  ADR-0008 (all staff see all — capability-gated), ADR-0009 (sensitive-data /
  metadata-only audit), ADR-0011 (invoice numbering: transaction-safe, not
  gap-free), ADR-0012 (issued invoices + payments immutable; corrections via
  credit note / reversal), ADR-0013 (`FeeAgreement`, not `Expense`),
  ADR-0018 (app layout / layering), ADR-0019 (object-level authz),
  ADR-0020 (audit), ADR-0021 (`NumberSequence`), ADR-0022 (soft-delete /
  no-hard-delete), ADR-0028 (`agenda` calendar extension point),
  ADR-0031 (contracts — the `value` seam), spec §37–42, §21, §97, §98, §82 Phase 8.
- **Phase:** 8

## Context

Spec §38–42 + §82 Phase 8: invoices (+ line items), payments (+ partial
payments / balances), expenses, "case fees". The money rules (§40, §42) and the
immutability / numbering decisions (ADR-0011/0012/0013) are already locked. Open
questions this ADR closes:

1. Are invoice totals stored or computed? How does that square with
   "issued = immutable" (ADR-0012)?
2. Is `متأخرة` (overdue) a stored status or computed (ADR-0006)?
3. How is overpayment prevented under concurrency (§40)?
4. What is the concrete credit-note / payment-reversal model?
5. Which roles see / manage finance?
6. Does finance data land on the case timeline / client profile / calendar /
   landing?

## Decision

### App — `finance` (one app, six models)

`FeeAgreement`, `Invoice`, `InvoiceLineItem`, `Payment`, `PaymentReversal`,
`CreditNote`. Standard layering (ADR-0018): `models` / `selectors` (scoped
reads) / `services` (transactional writes, audit, domain events) / thin views /
forms. All money is `Decimal`; all arithmetic is server-side (§42).

### Money representation

- `DecimalField(max_digits=14, decimal_places=2)` for amounts; `(5, 2)` for
  percentages (tax rate, contingency).
- `finance.money.quantize(x)` → `x.quantize(Decimal("0.01"), ROUND_HALF_UP)`.
  Applied to every stored monetary result (line totals, subtotal, tax, total).
- `currency` `Currency` `TextChoices` (ILS / JOD / USD / EUR), default ILS,
  reused from `contracts.models` conventions (a shared `core.money.Currency`).

### FeeAgreement — "رسوم القضايا" (ADR-0013)

`TimeStampedModel` + `AuthoredModel`. `reference` `FA-YYYY-NNNN` (assigned on
create, `editable=False`, unique, ADR-0021). FK `case` **PROTECT** (a fee
agreement is meaningless without its matter; the client is reached through the
case). `fee_type` `FeeType` `TextChoices`: `fixed` (مقطوع) / `hourly` (بالساعة) /
`contingency` (نسبة من المحصّل) / `retainer` (أتعاب دورية). Money fields, all
nullable, validated per `fee_type` in `clean()` + `CheckConstraint`:
`fixed_amount` (fixed / retainer), `hourly_rate` (hourly), `contingency_percent`
(contingency, 0–100). `currency`. `status` `FeeAgreementStatus`:
`draft` (مسودة) / `active` (سارية) / `completed` (منجزة) / `cancelled` (ملغاة) —
moves only through `change_fee_agreement_status` (`cancelled` terminal). Dates
(`agreed_on`, `start_date`, `end_date` — nullable), `description`, `notes`.
**No delete** (ADR-0022): `default_permissions = ("add", "change", "view")`.
`Invoice.fee_agreement` is an optional FK (ADR-0013 "invoices may reference the
governing agreement"). `FeeAgreement` records the *contracted* value; it does not
itself bill anything — invoices do.

### Invoice — stored totals, frozen at issue (ADR-0011, 0012)

`TimeStampedModel` + `AuthoredModel`. FK `client` **PROTECT / required**, FK
`case` **SET_NULL / optional**, FK `fee_agreement` **SET_NULL / optional**.

- **`invoice_number`** — `INV-YYYY-NNNN`, **assigned at issue** (ADR-0011), not on
  draft; `editable=False`, `unique`, `null=True` (drafts), gaps acceptable.
- **`status`** `InvoiceStatus`: `draft` (مسودة) / `unpaid` (غير مدفوعة) /
  `partially_paid` (مدفوعة جزئيًا) / `paid` (مدفوعة) / `cancelled` (ملغاة).
  The three payment states are **derived by the service** from `amount_paid` vs
  the credited total — never set by a form. `draft` and `cancelled` are explicit
  transitions.
- **`متأخرة` / overdue is COMPUTED, not stored (ADR-0006):** `Invoice.is_overdue`
  = `status in {unpaid, partially_paid}` and `due_date < today`.
  `InvoiceQuerySet.overdue()` mirrors it. The list, the landing widget and the
  client/case summaries read the property — there is **no cron and no `overdue`
  status** (unlike a contract's `expired`, which is a genuine lifecycle end;
  an invoice's overdue-ness flips back the moment it is paid).
- **Monetary fields are stored and the service keeps them correct**
  (`finance.services.recalculate_invoice`, draft only): `discount` (input,
  `≥ 0`, `≤ subtotal`), `tax_rate` (input percent, `≥ 0`), and the **computed
  snapshots** `subtotal` = Σ line totals, `tax_amount` =
  `quantize((subtotal − discount) × tax_rate/100)`, `total` =
  `subtotal − discount + tax_amount`. On **issue** these become immutable
  (ADR-0012) — the edit form and `services.update_invoice` refuse a non-draft
  invoice; there is no code path that mutates a line item or a monetary field of
  an issued invoice.
- **`amount_paid`** — maintained **only** by `finance.services` under
  `select_for_update` on the invoice row; never a form field.
- **`CheckConstraint`s:** every monetary field `≥ 0`; `discount ≤ subtotal`;
  `amount_paid ≤ total` (a DB-level backstop for the overpayment guard);
  `tax_rate` between 0 and 100.
- **No delete** (ADR-0022): `default_permissions = ("add", "change", "view")`,
  admin delete off. A **draft** may be `cancelled` directly; an **issued** invoice
  is corrected only by a `CreditNote` (a full-value credit note flips it to
  `cancelled`).

### InvoiceLineItem

FK `invoice` **CASCADE** (an aggregate-root child — ADR-0022 permits CASCADE
*within* a root). `description`, `quantity` `Decimal(10,2)` (`> 0`),
`unit_price` (`≥ 0`), `line_total` = `quantize(quantity × unit_price)` (stored,
frozen with the invoice). `position` for ordering. Added / removed only while the
invoice is `draft`, through dedicated `finance.services` calls (the `CaseParty`
add/remove idiom — **no formset**); each mutation re-runs
`recalculate_invoice` and writes an `INVOICE_UPDATED` audit event.

### Payment — immutable; overpayment-safe (§40, ADR-0012)

`TimeStampedModel` + `AuthoredModel`. `reference` `PMT-YYYY-NNNN` (on create,
`editable=False`, unique). FK `invoice` **PROTECT**. `amount` (`> 0`),
`paid_on` `DateField`, `method` `PaymentMethod` `TextChoices`
(cash / bank_transfer / cheque / card / other), `note` blank, `external_reference`
blank (cheque no. etc.). **Immutable:** `default_permissions = ("add", "view")`
— no change, no delete; admin add/change/delete all off. Corrections are a
`PaymentReversal`.

**`finance.services.record_payment`** — the whole overpayment guard:

```
with transaction.atomic():
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)   # row lock
    outstanding = invoice.credited_total - invoice.amount_paid         # both read under lock
    if amount <= 0 or amount > outstanding: raise ValidationError
    Payment.objects.create(...)
    invoice.amount_paid = F("amount_paid") + amount
    invoice.save(update_fields=["amount_paid"])
    invoice.refresh_from_db(fields=["amount_paid"])
    _apply_payment_status(invoice)        # unpaid / partially_paid / paid
```

Concurrent payments serialize on the `select_for_update` row lock; the DB
`amount_paid ≤ total` constraint is the backstop. Regression test uses a real
threads + `transaction=True` concurrency harness (only meaningful on PostgreSQL;
documented if the env is SQLite).

### PaymentReversal — void / correct a payment (ADR-0012)

FK `payment` **PROTECT**, `amount` (`> 0`, and `Σ reversals ≤ payment.amount`),
`reason`, `reversed_on`, `AuthoredModel`. Immutable (`("add", "view")`).
`finance.services.reverse_payment` — under `select_for_update` on the invoice:
`invoice.amount_paid −= amount`, recompute status, audit `PAYMENT_REVERSED`.

### CreditNote — correct an issued invoice (ADR-0012)

FK `invoice` **PROTECT**, `credit_number` `CN-YYYY-NNNN` (on create, unique),
`amount` (`> 0`, and `Σ credit notes ≤ invoice.total`), `reason`, `issued_on`,
`AuthoredModel`. Immutable (`("add", "view")`). Only against a **non-draft,
non-cancelled** invoice. `finance.services.issue_credit_note` — under
`select_for_update`: records the note; `Invoice.credited_total` (= `total − Σ
credit notes`) drops; payment status is recomputed against `credited_total`;
when `Σ credit notes == total` the invoice flips to `cancelled`. Credit notes
never touch `Payment` rows.

### Expense — money out, standalone (ADR-0013, spec §41)

`TimeStampedModel` + `AuthoredModel`. `reference` `EXP-YYYY-NNNN`. `description`,
`amount` (`> 0`), `category` `ExpenseCategory` `TextChoices` (court_fees /
government_fees / expert_fees / travel / office / translation / other),
`spent_on` `DateField`, FK `case` **SET_NULL / optional**, FK `client`
**SET_NULL / optional** (§41 — Office / Case / Client), `note`. **Editable**
(an expense is not "issued"). **Soft-delete** via `deleted_at` + `deleted_by`
(the documents/tasks idiom) — retained + audited, never hard-deleted;
`default_permissions = ("add", "change", "view")`, no `delete` codename.
**Expenses are never added to an invoice `total` or a fee agreement** — the spec
does not ask for it; financial reporting keeps money-in and money-out separate.

### Permissions (ADR-0007)

- **`finance.view`** — `office_manager`, `finance_clerk`, `lawyer`, `admin_clerk`.
  **`paralegal` has NO finance access** (§12 — "limited access to assigned
  work"). Covers every finance list + detail.
- **`finance.manage`** — `office_manager`, `finance_clerk` only (§12 — "موظف
  مالي: Financial operations"; the office manager has full access). Covers fee
  agreements, invoice draft/issue/cancel, line items, payments, reversals,
  credit notes, expenses.
- `sync_roles` maps the model codenames: `finance.{add,change,view}_feeagreement`
  / `{add,change,view}_invoice` / `{add,change,view}_invoicelineitem` /
  `{add,view}_payment` / `{add,view}_paymentreversal` / `{add,view}_creditnote` /
  `{add,change,view}_expense` — **no `delete` codename anywhere in finance**.

### Audit + case timeline (ADR-0009, 0020)

- `log_event` on every mutation, **metadata only** — `reference` / number /
  `status` / `amount` / `total` / changed-field names. `description` / `notes` /
  `reason` **bodies are never** in `changes`. New `AuditAction` members:
  `FEE_AGREEMENT_CREATED` / `_UPDATED` / `_STATUS_CHANGED`, `INVOICE_CREATED` /
  `_UPDATED` / `_ISSUED` / `_CANCELLED`, `PAYMENT_RECORDED` / `_REVERSED`,
  `CREDIT_NOTE_ISSUED`, `EXPENSE_CREATED` / `_UPDATED` / `_RETIRED`.
- django-auditlog registers `FeeAgreement`, `Invoice`, `Expense` (the editable
  ones) for the ordinary field diff.
- **Case timeline** (`cases.services.record_case_event`, `cases/0008`) when the
  record is case-linked: `FEE_AGREEMENT_ADDED`, `INVOICE_ISSUED`,
  `PAYMENT_RECORDED`, `CREDIT_NOTE_ISSUED`. Draft-invoice edits, expenses and
  reversals do **not** emit a `CaseEvent` (audit-only) — same rule as
  document/contract metadata edits.

### Integration

- **Client profile** (§21): the existing `finance_summary` placeholder
  (`{"invoiced": 0, "paid": 0, "outstanding": 0}`) becomes real —
  `finance.selectors.client_financials(client)` (Σ issued-invoice totals,
  Σ payments, outstanding). A **الفواتير** card (recent invoices + link) and a
  **المدفوعات** card. `العقود` / `الفواتير` / `المدفوعات` leave the client
  `disabled_tabs`.
- **Case workspace**: the disabled `الفواتير` / `المدفوعات` tabs become one real
  **المالية** tab — fee agreement, invoices, payments, outstanding for the case.
- **Landing** (§18 "المبالغ المستحقة"): a `المبالغ المستحقة` widget (outstanding
  issued invoices, overdue flagged) for `finance.view` holders, beside the
  Phase 5/7 widgets. The full operational dashboard is Phase 9.
- **Nav**: the **المالية** section (الفواتير / المدفوعات / المصروفات / رسوم
  القضايا) becomes live, gated on `finance.view`.
- **Calendar (ADR-0028):** `finance.selectors.calendar_items` yields one all-day
  event per **issued, unpaid/partially-paid** invoice on its `due_date`
  (`kind="invoice"`), appended to `agenda.selectors.calendar_events` — the same
  one-function extension ADR-0028/0029/0031 use.

## Consequences

- Stored totals mean an issued invoice is a stable, self-contained record; the
  `recalculate_invoice` service is the single writer while it is a draft.
- `amount_paid` denormalized + row-locked is what makes the overpayment guard
  race-safe without a separate ledger.
- Overdue never needs a scan; it also never goes stale the way a contract's
  `expired` can between `expire_contracts` runs.
- `CreditNote` + `PaymentReversal` give a complete, append-only correction story;
  no historical financial row is ever edited or deleted.
- A future **`Invoice`-from-`FeeAgreement`** helper (pre-filling a line item from
  the agreed fee) is additive. Fee roll-ups / revenue reports are Phase 10.
- Reimbursable-expense-on-invoice, multi-currency conversion, tax registration
  numbers, and a gap-free invoice sequence (ADR-0011) are explicit non-goals for
  v1 — scoped follow-ups if the office asks.
- Optimistic-locking tokens on draft-invoice edits (architecture §13 "design
  intent") are **not** built here — issued-invoice immutability plus the payment
  row lock cover the real concurrency risks; a draft is single-office-clerk work.
  Recorded as a possible future change.
