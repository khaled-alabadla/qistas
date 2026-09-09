"""Register task models with django-auditlog (docs/adr/0020)."""

from __future__ import annotations

from auditlog.registry import auditlog

from tasks.models import Deadline, Task

auditlog.register(Task, exclude_fields=["created_at", "updated_at"])
auditlog.register(Deadline, exclude_fields=["created_at", "updated_at"])
