# ADR-0013 — "رسوم القضايا" modelled as FeeAgreement, not Expense

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0012
- **Applies in:** Phase 8 (Finance). Not a Phase 1 concern.

## Context

The spec's navigation (§16) lists "رسوم القضايا" (case fees) under Finance, and Phase 8 scope mentions "Case fees". It was ambiguous whether this is a client-facing fee arrangement or an internal expense category.

## Decision

**"رسوم القضايا" is a `FeeAgreement` — the agreed legal fee between the office and the client for a matter.** It is **not** modelled as an `Expense` (expenses are costs the office incurs; fee agreements are revenue arrangements).

- A `FeeAgreement` is attached to a case (and thereby a client).
- It records the agreed basis: fixed, hourly, contingency (percentage), or retainer — final structure decided in the Finance phase.
- Invoices may reference the governing `FeeAgreement`.
- Detailed fields, lifecycle, and how agreements drive invoicing are finalized during Phase 8.

## Consequences

- Clear separation: `Expense` = money out; `FeeAgreement` + `Invoice` + `Payment` = money in.
- Financial reporting can distinguish contracted fee value from billed and collected amounts.
- Phase 8 owns the concrete model.
