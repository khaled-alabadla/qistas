# ADR-0014 — Conflict-of-interest checking deferred

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0015, grill D3

## Context

The grill noted that a law-practice system with no conflict-of-interest / privilege model risks letting a lawyer be assigned to both sides of a matter, or surfacing a client a staff member has a personal conflict with.

## Decision

**Automated conflict-of-interest checking is out of scope for v1.** It is a recorded deferred feature.

To keep the door open at low cost:
- The Cases phase (Phase 3) models parties (including opposing parties and opposing counsel) in **structured form** (`CaseParty` with roles), so a future conflict check is a query, not a schema migration.
- No conflict-checking logic, UI, or warnings are built in v1.

## Consequences

- The office relies on manual professional judgement for conflicts in v1 — acceptable to the owner.
- When conflict-checking is scoped, the structured party data is already there to build on.
