# ADR-0025 — Tiered testing strategy

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0010, ADR-0023, grill M1, M2

## Context

Spec §60 mandates a large test surface (concurrency, permissions, URL manipulation, finance edges, file access). For a solo phased build, "tests pass" in the Definition of Done is meaningless without a definition of *which* tests are non-negotiable.

## Decision

**Tooling:** `pytest-django`, `factory_boy`, `faker` (`ar_AA` locale with curated realistic Palestinian names — spec §61), `coverage`. Tests run on **PostgreSQL** (ADR-0023).

**Tiers:**
- **Tier 1 — blocks the phase (must be green):**
  - Authentication (login, logout, lockout, password change/reset, MFA enrollment).
  - Authorization — capability checks, object-level structural checks, URL-tampering (ADR-0019).
  - Money math & payment rules (from the Finance phase).
  - Reference-number concurrency (from the Clients phase).
  - Document access control (from the Documents phase).
  - Audit-write assertions for the phase's important actions.
- **Tier 2 — should have:** CRUD happy/validation paths, filters, search scoping, list pagination.
- **Tier 3 — nice to have:** UI state rendering, empty/loading/error states, edge formatting.

**Guards:** `assertNumQueries` on every heavy list/detail page as it is built. A `run_concurrently` helper for race tests. Coverage is **reported** (artifact) but only Tier-1 modules have a hard gate.

## Consequences

- A phase cannot be "complete" with a red Tier-1 test.
- The scope of testing per phase is explicit and reviewable.
- Phase 1 builds the harness (`conftest.py`, factories, `assert_*` helpers, `run_concurrently`, `assertNumQueries` wrapper) and the Tier-1 tests for the foundation (auth, authz framework, audit, errors, numbering concurrency).
