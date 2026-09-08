# ADR-0007 — RBAC via Django Groups + centralized capability layer

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0008, ADR-0019, grill B1, B4, X3

## Context

Spec §13 gives `User` a single `role` field. But spec §12/§46 describe permissions that can change ("Permission changed" is an audited event) and real offices have people who hold more than one role (the office manager is also a practising lawyer; a senior lawyer also approves finance). A single `role` enum forces one role per person and makes composable/editable access a painful later migration.

## Decision

**Django Groups are the source of truth for authorization. A user may belong to multiple groups.**

- Five groups seeded: `office_manager`, `lawyer`, `paralegal`, `admin_clerk`, `finance_clerk`.
- A **centralized capability layer** — `core/permissions/capabilities.py` — defines named capabilities (e.g. `cases.view`, `cases.edit`, `finance.view`, `clients.manage`) and maps groups → capabilities. `can(user, "cases.view")` resolves over the **union** of the user's groups. This layer is the *only* place capability logic lives, and it is fully unit-tested (truth table per group).
- Navigation and templates use `can()` for display; views enforce with `CapabilityRequiredMixin` / a `require_capability` decorator. **Display checks are never the enforcement.**
- An **idempotent `sync_roles` management command** owns the group→permission/capability mapping. It runs in CI (asserts no drift) and on deploy. Migrations create only the `Group` rows.
- **No `role` field on `User`** as a source of truth. If a denormalized "primary group" label is ever needed for display/filtering, it is derived, read-only, and never consulted for authorization.

## Consequences

- Diverges from spec §13's `role` field — recorded with owner approval.
- Adding/adjusting a capability is a code change + `sync_roles` run, reviewed and tested — not an ad-hoc DB edit.
- Multi-group users work naturally.
- Per-user permission overrides are **not** in v1 (groups only); can be added later via Django's per-user permissions without schema change.
- Phase 1 ships the capability layer, the 5 groups, `sync_roles`, and the enforcement mixins/decorator with tests — but no entity capabilities yet (no entities).
