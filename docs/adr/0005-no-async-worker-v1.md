# ADR-0005 — No async worker in v1; management commands + cron

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0027, grill X1

## Context

Several later features are time-based: task/invoice overdue surfacing, hearing/task/invoice/contract reminders, contract-expiry scans. The spec's stack (§9) lists no worker or broker. The grill flagged the mismatch and proposed `django-q2`. The owner has decided to keep the MVP infrastructure minimal.

## Decision

**No `django-q2`, no Celery, no Redis, no background worker in v1.**

- Time-based work is implemented as **idempotent Django management commands**, invoked by **system cron** in the deployment environment. Cron configuration is documented in the Production Readiness phase (Phase 14).
- Transactional email (password reset, later notifications-by-email if any) is sent **synchronously in the request** (Django's default behaviour) — acceptable at single-office volume.
- **Seam for future async:** `core/tasks.py` holds plain callables; each management command is a thin wrapper around one callable. Introducing a queue later means changing wrappers and adding an enqueue call — not touching business logic or callers.
- **Phase 1 schedules nothing.** Phase 1 has no time-based feature. It only creates the empty `core/tasks.py` and documents the pattern.

## Consequences

- Simplest possible deployment: one web process + Postgres. No worker to monitor.
- Reminders (Phase 11) will have cron-granularity latency (minutes), which is fine for a legal calendar.
- If real-time or high-volume needs appear, revisit with a dedicated ADR; the seam keeps that cheap.
- Long-running requests (large PDF/report exports, Phase 10) must be bounded or paginated since there is no worker to offload them.
