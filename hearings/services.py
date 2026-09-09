"""
Transactional writes for hearings (docs/adr/0018, 0028).

Every mutation:
* records a human-readable ``CaseEvent`` on the case timeline (spec §26) via
  ``cases.services.record_case_event``,
* writes an ``audit.AuditLog`` event (spec §46),
* **never deletes a row** — reschedule / hold / postpone / cancel are status
  transitions only (docs/adr/0022).

A held or postponed hearing that carries a next date spawns a **new scheduled
Hearing** for the same case, so it lands on the calendar, the timeline, and the
derived ``Case.next_hearing`` automatically.
"""

from __future__ import annotations

from datetime import datetime, time

from django.db import transaction
from django.utils import timezone

from audit.events import log_event
from audit.models import AuditAction
from cases.models import CaseEventType
from cases.services import record_case_event
from hearings.models import Hearing, HearingStatus

DEFAULT_START = time(9, 0)  # typical Palestinian court start (docs/adr/0028)

# Fields a user may edit directly on a still-scheduled hearing.
EDITABLE_FIELDS = ("scheduled_at", "hearing_type", "court", "lawyer", "room", "notes")


class HearingStateError(RuntimeError):
    """Raised when a lifecycle action is attempted on a hearing that is not in a
    valid state for it (e.g. completing an already-cancelled hearing)."""


def combine(d, t=None):
    """A date (+ optional time, default 09:00) → an aware datetime in the current tz."""
    naive = datetime.combine(d, t or DEFAULT_START)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _fmt(dt) -> str:
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")


def _require_open(hearing: Hearing) -> None:
    if hearing.status != HearingStatus.SCHEDULED:
        raise HearingStateError(f"Hearing {hearing.pk} is '{hearing.status}', not 'scheduled'.")


@transaction.atomic
def schedule_hearing(
    *,
    actor,
    case,
    scheduled_at,
    hearing_type,
    court=None,
    lawyer=None,
    room: str = "",
    notes: str = "",
    previous_hearing: Hearing | None = None,
    request=None,
) -> Hearing:
    hearing = Hearing(
        case=case,
        court=court,
        scheduled_at=scheduled_at,
        hearing_type=hearing_type,
        lawyer=lawyer,
        room=room,
        notes=notes,
        previous_hearing=previous_hearing,
        status=HearingStatus.SCHEDULED,
        created_by=actor,
        updated_by=actor,
    )
    hearing.full_clean()
    hearing.save()
    record_case_event(
        case,
        CaseEventType.HEARING_SCHEDULED,
        f"جلسة {hearing.get_hearing_type_display()} بتاريخ {_fmt(scheduled_at)}",
        actor=actor,
        hearing_id=hearing.pk,
    )
    log_event(
        request,
        AuditAction.HEARING_SCHEDULED,
        actor=actor,
        obj=hearing,
        changes={"case": case.case_number, "scheduled_at": _fmt(scheduled_at)},
    )
    return hearing


@transaction.atomic
def update_hearing(*, actor, hearing: Hearing, data: dict, request=None) -> Hearing:
    """Edit a still-scheduled hearing. A ``scheduled_at`` change is recorded as a
    reschedule; other field changes as a plain update."""
    _require_open(hearing)
    stored = Hearing.objects.select_related("court", "lawyer").get(pk=hearing.pk)
    data = {k: v for k, v in data.items() if k in EDITABLE_FIELDS}
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return hearing

    old_dt = stored.scheduled_at
    for field, value in data.items():
        setattr(hearing, field, value)
    hearing.updated_by = actor
    hearing.full_clean()
    hearing.save()

    if "scheduled_at" in changed:
        record_case_event(
            hearing.case,
            CaseEventType.HEARING_RESCHEDULED,
            f"أُعيدت جدولة الجلسة: {_fmt(old_dt)} ← {_fmt(hearing.scheduled_at)}",
            actor=actor,
            hearing_id=hearing.pk,
        )
        log_event(
            request,
            AuditAction.HEARING_RESCHEDULED,
            actor=actor,
            obj=hearing,
            changes={"scheduled_at": [_fmt(old_dt), _fmt(hearing.scheduled_at)]},
        )
    other = [f for f in changed if f != "scheduled_at"]
    if other:
        record_case_event(
            hearing.case,
            CaseEventType.HEARING_UPDATED,
            "تم تحديث بيانات الجلسة",
            actor=actor,
            hearing_id=hearing.pk,
            fields=sorted(other),
        )
        log_event(
            request,
            AuditAction.HEARING_UPDATED,
            actor=actor,
            obj=hearing,
            changes={"fields": sorted(other)},
        )
    return hearing


def _spawn_follow_up(*, actor, hearing, next_date, next_time, request) -> Hearing:
    return schedule_hearing(
        actor=actor,
        case=hearing.case,
        scheduled_at=combine(next_date, next_time),
        hearing_type=hearing.hearing_type,
        court=hearing.court,
        lawyer=hearing.lawyer,
        room=hearing.room,
        previous_hearing=hearing,
        request=request,
    )


@transaction.atomic
def complete_hearing(
    *,
    actor,
    hearing: Hearing,
    result: str = "",
    notes: str = "",
    next_action: str = "",
    next_hearing_date=None,
    next_hearing_time=None,
    request=None,
) -> Hearing:
    _require_open(hearing)
    hearing.status = HearingStatus.HELD
    hearing.result = result
    hearing.next_action = next_action
    hearing.next_hearing_date = next_hearing_date
    if notes:
        hearing.notes = notes
    hearing.updated_by = actor
    hearing.full_clean()
    hearing.save()

    record_case_event(
        hearing.case,
        CaseEventType.HEARING_HELD,
        f"عُقدت جلسة {hearing.get_hearing_type_display()} بتاريخ {_fmt(hearing.scheduled_at)}",
        actor=actor,
        hearing_id=hearing.pk,
    )
    log_event(
        request,
        AuditAction.HEARING_HELD,
        actor=actor,
        obj=hearing,
        changes={"next_hearing_date": str(next_hearing_date) if next_hearing_date else None},
    )
    if next_hearing_date:
        _spawn_follow_up(
            actor=actor,
            hearing=hearing,
            next_date=next_hearing_date,
            next_time=next_hearing_time,
            request=request,
        )
    return hearing


@transaction.atomic
def postpone_hearing(
    *,
    actor,
    hearing: Hearing,
    next_hearing_date,
    next_hearing_time=None,
    reason: str = "",
    next_action: str = "",
    request=None,
) -> Hearing:
    _require_open(hearing)
    if not next_hearing_date:
        raise HearingStateError("Postponing a hearing requires a next hearing date.")
    hearing.status = HearingStatus.POSTPONED
    hearing.next_hearing_date = next_hearing_date
    hearing.next_action = next_action
    if reason:
        hearing.notes = reason
    hearing.updated_by = actor
    hearing.full_clean()
    hearing.save()

    record_case_event(
        hearing.case,
        CaseEventType.HEARING_POSTPONED,
        f"أُجّلت جلسة {_fmt(hearing.scheduled_at)} إلى {next_hearing_date}",
        actor=actor,
        hearing_id=hearing.pk,
    )
    log_event(
        request,
        AuditAction.HEARING_POSTPONED,
        actor=actor,
        obj=hearing,
        changes={"next_hearing_date": str(next_hearing_date), "reason": reason},
    )
    _spawn_follow_up(
        actor=actor,
        hearing=hearing,
        next_date=next_hearing_date,
        next_time=next_hearing_time,
        request=request,
    )
    return hearing


@transaction.atomic
def cancel_hearing(*, actor, hearing: Hearing, reason: str = "", request=None) -> Hearing:
    _require_open(hearing)
    hearing.status = HearingStatus.CANCELLED
    if reason:
        hearing.notes = reason
    hearing.updated_by = actor
    hearing.full_clean()
    hearing.save()

    record_case_event(
        hearing.case,
        CaseEventType.HEARING_CANCELLED,
        f"أُلغيت جلسة {_fmt(hearing.scheduled_at)}",
        actor=actor,
        hearing_id=hearing.pk,
    )
    log_event(
        request,
        AuditAction.HEARING_CANCELLED,
        actor=actor,
        obj=hearing,
        changes={"reason": reason},
    )
    return hearing
