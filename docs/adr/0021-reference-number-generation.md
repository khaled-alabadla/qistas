# ADR-0021 — Reference-number generation (NumberSequence)

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0011, ADR-0022, grill H1
- **First real use:** Phase 2 (Clients). A framework scaffold may exist in `core` in Phase 1 with no consumers.

## Context

`case_number`, `client_number`, `invoice_number`, `contract_number` must be unique and race-safe. Naive approaches (`SEQUENCE`, `count()+1`, unguarded max+1) either always gap awkwardly, race, or serialize badly.

## Decision

- A **`NumberSequence(scope, period, last_value)`** table (`scope` e.g. `"client"`, `"case"`, `"invoice"`; `period` e.g. `""` or `"2026"`), one row per scope+period.
- Allocation: inside the same `transaction.atomic()` as the object insert — `select_for_update()` the sequence row, increment, use, save.
- Format: configurable prefix + optional period + zero-padded counter (e.g. `C-2026-0001`). Format config lives in settings/per-scope, not hard-coded.
- **Gaps are acceptable** (rolled-back transactions, cancelled drafts) — no gap-free machinery (ADR-0011).
- Reference numbers are **never reused**; a soft-deleted row keeps its number; the unique index is a **full** index, not partial (ADR-0022).
- `invoice_number` is allocated at **issue**, not on draft.
- **A real concurrency test is mandatory** (threads / `TransactionTestCase`) proving no duplicates and no lost increments under contention. `core/tests` provides a `run_concurrently` helper for this.

## Consequences

- One lock point per scope+period — fine at law-office write volume, and intentional.
- New-year rollover: the first insert of a new period creates that period's row under the same `select_for_update` discipline.
- No bare Postgres `SEQUENCE` (can't reset per period cleanly, always gaps regardless).
