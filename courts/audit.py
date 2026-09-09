"""Register court models with django-auditlog (docs/adr/0020)."""

from __future__ import annotations

from auditlog.registry import auditlog

from courts.models import Court

auditlog.register(Court)
