"""
Transactional writes for cases (docs/adr/0018, 0021).

Each mutation records a human-readable `CaseEvent` for the timeline (spec §26)
and an `audit.AuditLog` event for the compliance trail. Confidential-note changes
are audit-only (no timeline entry) so the visible timeline never hints at their
content.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from audit.events import log_event
from audit.models import AuditAction
from cases.models import (
    TERMINAL_STATUSES,
    Case,
    CaseConfidential,
    CaseEvent,
    CaseEventType,
    CaseLawyer,
    CaseNote,
    CaseParty,
    CaseStatus,
)
from core.numbering import format_reference, next_number

NUMBER_SCOPE = "case"


def allocate_case_number() -> str:
    period = str(timezone.localdate().year)
    return format_reference("CS", next_number(NUMBER_SCOPE, period=period), period=period)


def record_case_event(case, event_type, summary, *, actor=None, **detail) -> CaseEvent:
    return CaseEvent.objects.create(
        case=case, event_type=event_type, summary=summary, actor=actor, detail=detail
    )


def _who(user) -> str:
    if user is None:
        return "—"
    return user.get_full_name() or user.email


def _label(model, field, value) -> str:
    try:
        return dict(model._meta.get_field(field).choices)[value]
    except Exception:
        return str(value)


@transaction.atomic
def create_case(*, actor, data: dict, request=None) -> Case:
    case = Case(**data)
    case.case_number = allocate_case_number()
    case.created_by = actor
    case.updated_by = actor
    case.full_clean(exclude=["case_number"])
    case.save()
    record_case_event(case, CaseEventType.CREATED, f"أُنشئت القضية {case.case_number}", actor=actor)
    if case.assigned_lawyer_id:
        record_case_event(
            case,
            CaseEventType.LAWYER_ASSIGNED,
            f"المحامي المسؤول: {_who(case.assigned_lawyer)}",
            actor=actor,
        )
    log_event(request, AuditAction.CASE_CREATED, actor=actor, obj=case)
    return case


@transaction.atomic
def update_case(*, actor, case: Case, data: dict, request=None) -> Case:
    stored = Case.objects.select_related("type", "client", "assigned_lawyer", "court").get(
        pk=case.pk
    )
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return case

    lawyer_changed = "assigned_lawyer" in changed
    for field, value in data.items():
        setattr(case, field, value)
    case.updated_by = actor
    case.full_clean(exclude=["case_number"])
    case.save()

    record_case_event(
        case,
        CaseEventType.UPDATED,
        "تم تحديث بيانات القضية",
        actor=actor,
        fields=sorted(changed),
    )
    if lawyer_changed:
        record_case_event(
            case,
            CaseEventType.LAWYER_ASSIGNED,
            f"المحامي المسؤول: {_who(case.assigned_lawyer if case.assigned_lawyer_id else None)}",
            actor=actor,
        )
        log_event(request, AuditAction.CASE_LAWYER_CHANGED, actor=actor, obj=case)
    log_event(
        request,
        AuditAction.CASE_UPDATED,
        actor=actor,
        obj=case,
        changes={"fields": sorted(changed)},
    )
    return case


@transaction.atomic
def change_status(*, actor, case: Case, new_status: str, request=None) -> Case:
    if case.status == new_status:
        return case
    previous = case.status
    case.status = new_status
    case.updated_by = actor
    case.save(update_fields=["status", "updated_by", "updated_at"])

    if new_status == CaseStatus.CLOSED:
        etype = CaseEventType.CLOSED
    elif previous in TERMINAL_STATUSES and new_status not in TERMINAL_STATUSES:
        etype = CaseEventType.REOPENED
    else:
        etype = CaseEventType.STATUS_CHANGED
    record_case_event(
        case,
        etype,
        f"الحالة: {_label(Case, 'status', previous)} ← {_label(Case, 'status', new_status)}",
        actor=actor,
    )
    log_event(
        request,
        AuditAction.CASE_STATUS_CHANGED,
        actor=actor,
        obj=case,
        changes={"status": [previous, new_status]},
    )
    return case


@transaction.atomic
def add_supporting_lawyer(*, actor, case: Case, lawyer, request=None) -> bool:
    _obj, created = CaseLawyer.objects.get_or_create(
        case=case, lawyer=lawyer, defaults={"added_by": actor}
    )
    if not created:
        return False
    who = _who(lawyer)
    record_case_event(case, CaseEventType.LAWYER_ADDED, f"محامٍ مساند: {who}", actor=actor)
    log_event(
        request,
        AuditAction.CASE_LAWYER_CHANGED,
        actor=actor,
        obj=case,
        changes={"supporting_added": who},
    )
    return True


@transaction.atomic
def remove_supporting_lawyer(*, actor, case: Case, lawyer, request=None) -> bool:
    deleted, _ = CaseLawyer.objects.filter(case=case, lawyer=lawyer).delete()
    if not deleted:
        return False
    who = _who(lawyer)
    record_case_event(case, CaseEventType.LAWYER_REMOVED, f"أُزيل محامٍ مساند: {who}", actor=actor)
    log_event(
        request,
        AuditAction.CASE_LAWYER_CHANGED,
        actor=actor,
        obj=case,
        changes={"supporting_removed": who},
    )
    return True


@transaction.atomic
def add_party(*, actor, case: Case, data: dict, request=None) -> CaseParty:
    party = CaseParty(case=case, added_by=actor, **data)
    party.full_clean(exclude=["case", "added_by"])
    party.save()
    record_case_event(
        case,
        CaseEventType.PARTY_ADDED,
        f"{party.get_party_role_display()}: {party.name}",
        actor=actor,
    )
    log_event(
        request,
        AuditAction.CASE_PARTY_CHANGED,
        actor=actor,
        obj=case,
        changes={"party_added": party.name, "role": party.party_role},
    )
    return party


@transaction.atomic
def remove_party(*, actor, case: Case, party: CaseParty, request=None) -> None:
    name, role = party.name, party.get_party_role_display()
    party.delete()
    record_case_event(case, CaseEventType.PARTY_REMOVED, f"أُزيل الطرف: {name}", actor=actor)
    log_event(
        request,
        AuditAction.CASE_PARTY_CHANGED,
        actor=actor,
        obj=case,
        changes={"party_removed": name, "role": role},
    )


@transaction.atomic
def add_note(*, actor, case: Case, body: str, kind: str, request=None) -> CaseNote:
    note = CaseNote.objects.create(case=case, body=body, kind=kind, author=actor)
    record_case_event(
        case, CaseEventType.NOTE_ADDED, f"{note.get_kind_display()} جديدة", actor=actor
    )
    log_event(request, AuditAction.CASE_NOTE_ADDED, actor=actor, obj=case, changes={"kind": kind})
    return note


@transaction.atomic
def set_confidential(
    *, actor, case: Case, legal_notes: str, internal_notes: str, request=None
) -> CaseConfidential:
    conf, _created = CaseConfidential.objects.get_or_create(case=case)
    if conf.legal_notes == legal_notes and conf.internal_notes == internal_notes:
        return conf
    conf.legal_notes = legal_notes
    conf.internal_notes = internal_notes
    conf.updated_by = actor
    conf.save()
    # Audit only — deliberately NOT a CaseEvent (the timeline is visible to all staff).
    log_event(
        request,
        AuditAction.CASE_CONFIDENTIAL_UPDATED,
        actor=actor,
        obj=case,
        changes={"fields": ["legal_notes", "internal_notes"]},
    )
    return conf
