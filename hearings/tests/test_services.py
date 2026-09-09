from datetime import date, time, timedelta

import pytest
from django.utils import timezone

from audit.models import AuditAction, AuditLog
from cases.models import CaseEventType
from cases.tests.factories import CaseFactory
from hearings import services
from hearings.models import Hearing, HearingStatus
from hearings.tests.factories import HearingFactory

pytestmark = pytest.mark.django_db


def _future_dt(days=7):
    return timezone.now() + timedelta(days=days)


def test_schedule_hearing_creates_row_event_and_audit(office_manager):
    case = CaseFactory()
    h = services.schedule_hearing(
        actor=office_manager,
        case=case,
        scheduled_at=_future_dt(),
        hearing_type="first_session",
    )
    assert h.status == HearingStatus.SCHEDULED
    assert h.created_by == office_manager
    assert case.events.filter(event_type=CaseEventType.HEARING_SCHEDULED).exists()
    assert AuditLog.objects.filter(
        action=AuditAction.HEARING_SCHEDULED, entity_id=str(h.pk)
    ).exists()


def test_update_hearing_records_reschedule_when_datetime_changes(office_manager):
    h = HearingFactory()
    new_dt = _future_dt(14)
    services.update_hearing(
        actor=office_manager,
        hearing=h,
        data={"scheduled_at": new_dt, "hearing_type": h.hearing_type},
    )
    h.refresh_from_db()
    assert h.scheduled_at == new_dt
    assert h.case.events.filter(event_type=CaseEventType.HEARING_RESCHEDULED).exists()


def test_update_hearing_noop_when_nothing_changed(office_manager):
    h = HearingFactory(room="A")
    before = h.case.events.count()
    services.update_hearing(
        actor=office_manager,
        hearing=h,
        data={"scheduled_at": h.scheduled_at, "hearing_type": h.hearing_type, "room": "A"},
    )
    assert h.case.events.count() == before


def test_update_hearing_rejected_on_closed_hearing(office_manager):
    h = HearingFactory(status=HearingStatus.CANCELLED)
    with pytest.raises(services.HearingStateError):
        services.update_hearing(
            actor=office_manager, hearing=h, data={"room": "B", "hearing_type": h.hearing_type}
        )


def test_complete_hearing_without_next_date(office_manager):
    h = HearingFactory()
    services.complete_hearing(actor=office_manager, hearing=h, result="تأجيل للبينة")
    h.refresh_from_db()
    assert h.status == HearingStatus.HELD
    assert h.result == "تأجيل للبينة"
    assert Hearing.objects.filter(case=h.case).count() == 1
    assert h.case.events.filter(event_type=CaseEventType.HEARING_HELD).exists()


def test_complete_hearing_with_next_date_spawns_follow_up(office_manager):
    h = HearingFactory()
    services.complete_hearing(
        actor=office_manager,
        hearing=h,
        next_hearing_date=date.today() + timedelta(days=30),
        next_hearing_time=time(10, 30),
    )
    follow = Hearing.objects.filter(case=h.case).exclude(pk=h.pk).get()
    assert follow.status == HearingStatus.SCHEDULED
    assert follow.previous_hearing_id == h.pk
    assert timezone.localtime(follow.scheduled_at).hour == 10
    # the derived next hearing now points at the follow-up
    assert h.case.next_hearing == follow


def test_postpone_requires_next_date(office_manager):
    h = HearingFactory()
    with pytest.raises(services.HearingStateError):
        services.postpone_hearing(actor=office_manager, hearing=h, next_hearing_date=None)


def test_postpone_hearing_spawns_follow_up_and_events(office_manager):
    h = HearingFactory()
    services.postpone_hearing(
        actor=office_manager,
        hearing=h,
        next_hearing_date=date.today() + timedelta(days=20),
        reason="غياب الخصم",
    )
    h.refresh_from_db()
    assert h.status == HearingStatus.POSTPONED
    assert h.notes == "غياب الخصم"
    assert Hearing.objects.filter(case=h.case, status=HearingStatus.SCHEDULED).count() == 1
    assert h.case.events.filter(event_type=CaseEventType.HEARING_POSTPONED).exists()


def test_cancel_hearing_keeps_row(office_manager):
    h = HearingFactory()
    services.cancel_hearing(actor=office_manager, hearing=h, reason="سحب الدعوى")
    h.refresh_from_db()
    assert h.status == HearingStatus.CANCELLED
    assert Hearing.objects.filter(pk=h.pk).exists()
    assert h.case.events.filter(event_type=CaseEventType.HEARING_CANCELLED).exists()
    assert AuditLog.objects.filter(
        action=AuditAction.HEARING_CANCELLED, entity_id=str(h.pk)
    ).exists()


def test_completed_hearing_cannot_be_completed_again(office_manager):
    h = HearingFactory()
    services.complete_hearing(actor=office_manager, hearing=h)
    with pytest.raises(services.HearingStateError):
        services.cancel_hearing(actor=office_manager, hearing=h)
