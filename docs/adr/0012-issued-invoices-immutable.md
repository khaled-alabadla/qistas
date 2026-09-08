# ADR-0012 — Issued invoices are immutable; corrections via credit note

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0011, grill F1
- **Applies in:** Phase 8 (Finance). Not a Phase 1 concern.

## Context

A `total` computed from line items can change after payments are recorded, breaking constraints or silently desynchronizing the record. Legal/accounting practice requires that issued financial documents not be edited in place.

## Decision

- Once an invoice **leaves `draft` (is issued)**, its line items and monetary fields are **immutable**. Enforced in the service layer and, where practical, a DB trigger.
- Corrections are made through a proper **correction / credit-note mechanism** — a new linked financial document — never by editing the issued invoice.
- Payments are likewise immutable; corrections use a `PaymentReversal` (Finance phase).
- **The full correction / credit-note workflow is built in the Finance phase (Phase 8), not Phase 1.** Phase 1 introduces no finance models.

## Consequences

- Auditable, stable financial history.
- Draft invoices remain fully editable.
- The Finance phase must design the credit-note model, its numbering, its effect on client balances, and its reporting before the phase is complete.
