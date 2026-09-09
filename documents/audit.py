"""Register Document with django-auditlog (docs/adr/0020, 0030).

The ``file`` field is excluded and the diff is metadata only — file contents
never enter the audit trail (ADR-0009, architecture field-diff allowlist).
"""

from __future__ import annotations

from auditlog.registry import auditlog

from documents.models import Document

auditlog.register(
    Document,
    exclude_fields=["created_at", "updated_at", "file", "content_type", "size", "sha256"],
)
