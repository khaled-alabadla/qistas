"""`log_event` — the single entry point for writing an explicit audit event."""

from __future__ import annotations

import ipaddress
from typing import Any

from django.conf import settings

from audit.models import AuditLog
from core.sensitive import redact


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _client_ip(request) -> str | None:
    """The connecting address. ``X-Forwarded-For`` is client-controlled and is
    trusted ONLY when ``AUDIT_TRUST_XFF`` is set (i.e. a trusted proxy strips
    and re-sets it) — otherwise a forged header could frame an IP in the
    append-only audit trail."""
    if request is None:
        return None
    if getattr(settings, "AUDIT_TRUST_XFF", False):
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        first = xff.split(",")[0] if xff else ""
        ip = _valid_ip(first)
        if ip:
            return ip
    return _valid_ip(request.META.get("REMOTE_ADDR"))


def log_event(
    request,
    action: str,
    *,
    actor=None,
    obj: Any = None,
    changes: dict | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    object_repr: str | None = None,
) -> AuditLog:
    """Record an audit event. Sensitive values in ``changes`` are redacted
    (docs/adr/0009) — pass field names, not secret values."""
    if actor is None and request is not None:
        user = getattr(request, "user", None)
        actor = user if getattr(user, "is_authenticated", False) else None

    if obj is not None:
        entity_type = entity_type or f"{obj._meta.app_label}.{obj._meta.model_name}"
        entity_id = entity_id or str(getattr(obj, "pk", "") or "")
        object_repr = object_repr or str(obj)[:200]

    ua = ""
    if request is not None:
        ua = request.META.get("HTTP_USER_AGENT", "")[:300]

    return AuditLog.objects.create(
        actor=actor,
        action=str(action),
        entity_type=entity_type or "",
        entity_id=entity_id or "",
        object_repr=object_repr or "",
        changes=redact(changes),
        ip_address=_client_ip(request),
        user_agent=ua,
    )
