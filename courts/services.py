"""Transactional writes for courts (docs/adr/0018, 0028).

django-auditlog records the field-level diff (``courts.audit``); these services
add a plain-language ``audit.AuditLog`` event. Courts are not case-scoped, so no
``CaseEvent`` is written. A court is never deleted — deactivation is an
``is_active`` toggle (docs/adr/0022).
"""

from __future__ import annotations

from django.db import transaction

from audit.events import log_event
from audit.models import AuditAction
from courts.models import Court


@transaction.atomic
def create_court(*, actor, data: dict, request=None) -> Court:
    court = Court(**data)
    court.full_clean()
    court.save()
    log_event(request, AuditAction.COURT_CREATED, actor=actor, obj=court)
    return court


@transaction.atomic
def update_court(*, actor, court: Court, data: dict, request=None) -> Court:
    # Diff against the persisted row — a ModelForm mutates its instance during
    # is_valid(), so the passed `court` may already carry the new values.
    stored = Court.objects.get(pk=court.pk)
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return court

    for field, value in data.items():
        setattr(court, field, value)
    court.full_clean()
    court.save()
    log_event(
        request,
        AuditAction.COURT_UPDATED,
        actor=actor,
        obj=court,
        changes={"fields": sorted(changed)},
    )
    return court


@transaction.atomic
def set_active(*, actor, court: Court, is_active: bool, request=None) -> Court:
    if court.is_active == is_active:
        return court
    court.is_active = is_active
    court.save(update_fields=["is_active"])
    log_event(
        request,
        AuditAction.COURT_ACTIVATED if is_active else AuditAction.COURT_DEACTIVATED,
        actor=actor,
        obj=court,
        changes={"is_active": is_active},
    )
    return court
