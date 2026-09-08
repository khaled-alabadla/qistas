# ADR-0011 — Invoice numbering: transaction-safe unique, not gap-free

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0021, grill H1
- **Applies in:** Phase 8 (Finance). Not a Phase 1 concern.

## Context

Some jurisdictions/accountants require strictly gap-free invoice sequences (a rolled-back transaction that consumed a number would need a compensating "voided number" record). This adds real complexity. The owner has confirmed it is not required for Palestine v1 unless proven otherwise later.

## Decision

- Invoice references are **transaction-safe and unique**, generated via the `NumberSequence` mechanism (ADR-0021), assigned at **issue** (not on draft).
- **Gap-free is NOT a requirement for v1.** Gaps from rolled-back transactions or cancelled drafts are acceptable and documented for the office's accountant.
- No "voided number" / compensating-record machinery is built.

## Consequences

- Simpler, race-safe numbering.
- If a later legal/accounting requirement proves gap-free numbering is mandatory, that is a scoped follow-up: add a compensating record on sequence-consume failure and an audit of number voids. Recorded as a known possible future change.
