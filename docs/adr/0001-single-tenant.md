# ADR-0001 — Single-tenant architecture for v1

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0019, `QISTAS_GRILL_REVIEW.md` P1

## Context

The spec refers to "law offices" (plural) but describes one office's operations. Multi-tenancy is the single most invasive architectural choice: it puts a tenant discriminator on every table and threads tenant scoping through every query and permission check. Retrofitting it later is expensive; pre-building it for a single customer is wasted cost and complexity.

## Decision

**Qistas v1 is single-tenant: one law office per deployment.** No `Office` / `Tenant` model and no tenant foreign key on any model. Isolation between offices, if ever required, is achieved by running separate deployments (separate database, separate storage).

Multi-tenancy is **not** pre-built and **not** approximated. It is recorded here as a possible future migration whose shape is: introduce a `Tenant` model, add a nullable-then-required FK to root models via data migration, convert `for_user()` scopers to tenant-aware equivalents, partition large tables.

## Consequences

- Models stay simple; queries stay simple; no tenant-scoping bugs.
- Every deployment is one office. Onboarding a second office = a new deployment.
- If SaaS becomes a goal, it is a planned project, not an incremental change. Accepted.
- Domain code must not bake in assumptions that would *block* a future tenant column (e.g. globally unique natural keys are fine; cross-office logic must not be assumed absent in a way that's unrecoverable — but for v1 there is no cross-office anything).
