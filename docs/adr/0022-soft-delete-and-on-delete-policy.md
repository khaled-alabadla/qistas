# ADR-0022 — Soft-delete, archival, and on_delete policy

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0021, grill G1, G2, X5
- **Policy binding now; applied per entity in each phase.**

## Context

Spec §57 warns against casual cascade deletes of legal records; §55 wants normalization; §21/§26 want full related history shown. The grill flagged that universal soft-delete fights `PROTECT` FKs, unique constraints, and "show all history", and that a blanket "never CASCADE" is wrong for true aggregate parts.

## Decision

**Soft-delete** applies to a **small named set** of models only. Initial set: `Task`, `Note`, `Document` (revisited as each phase adds models; additions require updating this ADR). These get `deleted_at` + a manager exposing `active` (default) and `all_with_deleted`.

**Archival, not deletion, for `Case` and `Client`:** "archived" is a **status value**. The record stays visible in history, pickers exclude it. True deletion of a `Case`/`Client` is a rare admin action gated by capability and requiring reassignment of dependents — not a routine soft-delete.

**Never soft-deleted / never routinely deleted:** `Invoice`, `Payment`, `Hearing`, `Contract`, `AuditLog`.

**Reference numbers** use **full** unique indexes (not `WHERE deleted_at IS NULL`) — numbers are never reused; a soft-deleted/archived row keeps its number.

**`on_delete` policy:**
- `CASCADE` **only within an aggregate root** — e.g. `InvoiceLineItem → Invoice`, `CaseParty → Case`, `CaseLawyer → Case`.
- `PROTECT` for references to legally significant records (`Case`, `Client`, `Invoice`, `Contract`, `Hearing`).
- `SET_NULL` for actor/author references (`created_by`, `uploaded_by`, `actor`) so deactivating a user never destroys history.
- **Never `CASCADE` into** `Case`, `Hearing`, `Invoice`, `Payment`, `Document`, `Contract`, `AuditLog`.

## Consequences

- Two query modes (`active` / `all_with_deleted`) exist only for the small soft-delete set, not everywhere.
- Timelines and audit can still surface archived/soft-deleted items; list pickers filter them out.
- Each entity phase states, in its DoD, which policy row applies to its models.
