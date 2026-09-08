# ADR-0015 — Client portal deferred

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0004, ADR-0019

## Context

The spec never mentions clients logging in. The grill asked for confirmation because a client portal changes the auth model, permissions, and data exposure surface significantly.

## Decision

**A client portal (clients authenticating and viewing their own cases/invoices/documents) is out of scope for v1.** Recorded as a deferred feature.

- `Client` is a domain record, **not** a `User`. No `client` role, no client login.
- All Qistas users are office staff.
- The authorization model (ADR-0007, ADR-0019) is designed for staff roles only.

## Consequences

- Simpler auth and permission surface for v1.
- If a portal is added later it is a substantial project: a separate authentication path, a strictly-scoped client-facing permission layer, careful data-exposure review, and likely a separate URL namespace/app. Not an incremental change.
