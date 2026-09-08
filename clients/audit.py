"""Register Client with django-auditlog (docs/adr/0020).

Identity numbers are masked in the diff (docs/adr/0009 — they are in
`core.sensitive.SENSITIVE_FIELDS`); `notes` is excluded because internal notes
should not be copied into the audit trail. Timestamps are noise.
"""

from __future__ import annotations

from auditlog.registry import auditlog

from clients.models import Client
from core.sensitive import SENSITIVE_FIELDS

_MASK = sorted(f for f in SENSITIVE_FIELDS if hasattr(Client, f))

auditlog.register(
    Client,
    exclude_fields=["created_at", "updated_at", "notes"],
    mask_fields=_MASK,
)
