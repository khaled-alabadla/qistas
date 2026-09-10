"""Register the contract model with django-auditlog (docs/adr/0020)."""

from __future__ import annotations

from auditlog.registry import auditlog

from contracts.models import Contract

auditlog.register(Contract, exclude_fields=["created_at", "updated_at"])
