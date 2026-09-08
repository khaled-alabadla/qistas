import pytest

from audit.models import AuditAction, AuditLog
from cases import services
from cases.models import CaseEvent, CaseEventType, CaseStatus
from cases.tests.factories import CaseFactory, CaseTypeFactory
from clients.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


def _data(**over):
    d = {
        "title": "قضية جديدة",
        "type": CaseTypeFactory(),
        "client": ClientFactory(),
        "priority": "medium",
    }
    d.update(over)
    return d


def test_create_case_allocates_number_and_logs(office_manager):
    case = services.create_case(actor=office_manager, data=_data())
    assert case.case_number.startswith("CS-")
    assert case.created_by == office_manager
    assert case.events.filter(event_type=CaseEventType.CREATED).exists()
    assert AuditLog.objects.filter(action=AuditAction.CASE_CREATED, entity_id=str(case.pk)).exists()


def test_create_case_with_lawyer_records_assignment_event(office_manager, lawyer):
    case = services.create_case(actor=office_manager, data=_data(assigned_lawyer=lawyer))
    assert case.events.filter(event_type=CaseEventType.LAWYER_ASSIGNED).exists()


def test_update_case_noop_when_nothing_changed(office_manager):
    case = services.create_case(actor=office_manager, data=_data())
    before = CaseEvent.objects.filter(case=case).count()
    services.update_case(
        actor=office_manager,
        case=case,
        data={"title": case.title, "priority": case.priority},
    )
    assert CaseEvent.objects.filter(case=case).count() == before


def test_update_case_records_changed_fields(office_manager):
    case = services.create_case(actor=office_manager, data=_data())
    services.update_case(actor=office_manager, case=case, data={"title": "عنوان معدّل"})
    case.refresh_from_db()
    assert case.title == "عنوان معدّل"
    ev = case.events.filter(event_type=CaseEventType.UPDATED).first()
    assert ev and "title" in ev.detail["fields"]


def test_change_status_to_closed_emits_closed_event(office_manager):
    case = services.create_case(actor=office_manager, data=_data())
    services.change_status(actor=office_manager, case=case, new_status=CaseStatus.CLOSED)
    case.refresh_from_db()
    assert case.status == CaseStatus.CLOSED
    assert case.events.filter(event_type=CaseEventType.CLOSED).exists()


def test_reopen_from_terminal_emits_reopened_event(office_manager):
    case = CaseFactory(status=CaseStatus.CONCLUDED)
    services.change_status(actor=office_manager, case=case, new_status=CaseStatus.IN_PROGRESS)
    assert case.events.filter(event_type=CaseEventType.REOPENED).exists()


def test_add_and_remove_party(office_manager):
    case = CaseFactory()
    party = services.add_party(
        actor=office_manager,
        case=case,
        data={"party_role": "opponent", "name": "خصم الاختبار"},
    )
    assert case.parties.count() == 1
    assert case.events.filter(event_type=CaseEventType.PARTY_ADDED).exists()
    services.remove_party(actor=office_manager, case=case, party=party)
    assert case.parties.count() == 0
    assert case.events.filter(event_type=CaseEventType.PARTY_REMOVED).exists()


def test_add_and_remove_supporting_lawyer(office_manager, lawyer):
    case = CaseFactory()
    assert services.add_supporting_lawyer(actor=office_manager, case=case, lawyer=lawyer) is True
    assert case.supporting_lawyers.filter(pk=lawyer.pk).exists()
    # idempotent — second add is a no-op and reports it
    assert services.add_supporting_lawyer(actor=office_manager, case=case, lawyer=lawyer) is False
    assert case.lawyer_links.count() == 1
    assert services.remove_supporting_lawyer(actor=office_manager, case=case, lawyer=lawyer) is True
    assert not case.supporting_lawyers.exists()
    # removing again reports nothing happened
    assert (
        services.remove_supporting_lawyer(actor=office_manager, case=case, lawyer=lawyer) is False
    )


def test_add_note(office_manager):
    case = CaseFactory()
    services.add_note(actor=office_manager, case=case, body="ملاحظة", kind="general")
    assert case.notes.count() == 1
    assert case.events.filter(event_type=CaseEventType.NOTE_ADDED).exists()


def test_set_confidential_is_audit_only_no_timeline_event(office_manager):
    case = CaseFactory()
    services.set_confidential(
        actor=office_manager,
        case=case,
        legal_notes="سري",
        internal_notes="داخلي",
    )
    assert case.confidential.legal_notes == "سري"
    assert not case.events.exists()  # deliberately no CaseEvent
    assert AuditLog.objects.filter(
        action=AuditAction.CASE_CONFIDENTIAL_UPDATED, entity_id=str(case.pk)
    ).exists()


def test_set_confidential_noop_when_unchanged(office_manager):
    case = CaseFactory()
    services.set_confidential(actor=office_manager, case=case, legal_notes="a", internal_notes="")
    services.set_confidential(actor=office_manager, case=case, legal_notes="a", internal_notes="")
    assert AuditLog.objects.filter(action=AuditAction.CASE_CONFIDENTIAL_UPDATED).count() == 1
