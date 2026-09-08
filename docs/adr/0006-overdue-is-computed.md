# ADR-0006 — "Overdue" is a computed state, not a stored status

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0005, grill X2

## Context

Spec §31 lists `متأخرة` (overdue) as a Task **status** value; §39 lists `متأخرة` as an Invoice status. Spec §32 says overdue must be *derived* server-side (`due_date < today AND status != completed`). A stored "overdue" status needs a job to flip it and can drift; a derived state cannot drift and needs no job.

## Decision

**Overdue is always a computed state.**

- Task stored status enum: `new`, `in_progress`, `done`, `cancelled` — **no `overdue`**.
- Invoice stored status enum (Finance phase): `draft`, `unpaid`, `partial`, `paid`, `cancelled` — **no `overdue`**.
- "Overdue" is a model property / queryset annotation (`due_date < today AND status not in {done, cancelled}`), used for list filters, dashboard buckets, and reports.
- Because it is computed, **no cron job is needed** to maintain it (consistent with ADR-0005). If a materialized flag is ever wanted for performance, that is a separate decision.

## Consequences

- Diverges from the literal spec enums in §31/§39 — recorded here with owner approval.
- Notifications for "task overdue" / "invoice overdue" (Phase 11) are produced by a scanning management command that queries the computed condition; the notification is the artifact, not a status change.
- Filters/reports must use the shared annotation helper, not ad-hoc date logic, to stay consistent.
