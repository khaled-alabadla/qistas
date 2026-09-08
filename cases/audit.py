"""Register case models with django-auditlog (docs/adr/0020).

`CaseConfidential.legal_notes` / `internal_notes` are in
`core.sensitive.SENSITIVE_FIELDS` and masked here so privileged legal content
never lands verbatim in the audit trail.
"""

from __future__ import annotations

from auditlog.registry import auditlog

from cases.models import Case, CaseConfidential, CaseParty
from core.sensitive import SENSITIVE_FIELDS

auditlog.register(Case, exclude_fields=["created_at", "updated_at"])
auditlog.register(CaseParty, exclude_fields=["created_at"])
auditlog.register(
    CaseConfidential,
    exclude_fields=["updated_at"],
    mask_fields=sorted(f for f in SENSITIVE_FIELDS if hasattr(CaseConfidential, f)),
)
