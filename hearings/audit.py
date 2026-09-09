"""Register hearing models with django-auditlog (docs/adr/0020)."""

from __future__ import annotations

from auditlog.registry import auditlog

from hearings.models import Hearing

auditlog.register(Hearing, exclude_fields=["created_at", "updated_at"])
