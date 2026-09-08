"""
Async / scheduled-work seam (docs/adr/0005).

Qistas v1 has **no worker and no broker**. Time-based work (overdue scans,
reminders, contract-expiry checks — all future phases) is implemented as plain
callables here, each wrapped by a thin Django management command that system
cron invokes in the deployment.

Rules:
* Functions in this module take no request and must be **idempotent**.
* A management command is a one-line wrapper: ``core.tasks.<fn>()``.
* Introducing a queue later (django-q2 / Celery) means changing the wrappers to
  enqueue — callers and business logic do not change.

Phase 1 schedules nothing; this module is intentionally empty.
"""

from __future__ import annotations

__all__: list[str] = []
