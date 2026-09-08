# ADR-0010 — Security/audit/testing/a11y/perf in every phase DoD; Phases 12/13 are hardening

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** all ADRs; grill P4

## Context

The spec's phase list makes Phase 12 "Audit + Advanced Security" and Phase 13 "Quality + Performance + UX". Read as "security comes at the end", that means 11 phases of code to retrofit. But spec §54 calls security first-class and §79's Definition of Done already lists "security reviewed / performance reviewed / permissions tested" per phase.

## Decision

**Security, authorization, audit, testing, accessibility, and performance are part of the Definition of Done of every relevant phase — never postponed.**

For each phase that introduces an entity or view, the DoD includes:
- Object-level authorization enforced (ADR-0019) and covered by permission-matrix + URL-tampering tests.
- Audit wired for the entity's important actions (ADR-0020).
- Tier-1 tests green (ADR-0025).
- `assertNumQueries` guards on any heavy list/detail page introduced.
- Accessibility basics (labels, focus, semantic HTML, contrast, not-color-only status) on new UI.
- `manage.py check --deploy` stays clean.

**Phases 12 and 13 are hardening / review passes** — they deepen and verify (DB-level audit immutability, rate-limiting, full permission re-review, N+1 sweep, a11y audit, UX polish), not the first time these concerns are addressed.

## Consequences

- Slightly more work per phase; far less rework overall.
- A phase cannot be reported "complete" with known unaddressed authz/audit gaps in its own scope.
- The Phase Completion Report (spec §76) explicitly states the security/audit/test/a11y/perf status for that phase.
