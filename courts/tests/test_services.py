import pytest

from audit.models import AuditAction, AuditLog
from cases.tests.factories import CourtFactory
from courts import services
from courts.models import Court

pytestmark = pytest.mark.django_db


def _data(**over):
    d = {"name": "محكمة بداية طولكرم", "type": "first_instance", "city": "طولكرم"}
    d.update(over)
    return d


def test_create_court_logs_audit(office_manager):
    court = services.create_court(actor=office_manager, data=_data())
    assert court.pk
    assert AuditLog.objects.filter(
        action=AuditAction.COURT_CREATED, entity_id=str(court.pk)
    ).exists()


def test_update_court_noop_when_unchanged(office_manager):
    court = CourtFactory(name="أ", city="ب")
    services.update_court(actor=office_manager, court=court, data={"name": "أ", "city": "ب"})
    assert not AuditLog.objects.filter(action=AuditAction.COURT_UPDATED).exists()


def test_update_court_records_changed_fields(office_manager):
    court = CourtFactory()
    services.update_court(
        actor=office_manager, court=court, data={"phone": "09-1234567", "name": court.name}
    )
    court.refresh_from_db()
    assert court.phone == "09-1234567"
    log = AuditLog.objects.get(action=AuditAction.COURT_UPDATED, entity_id=str(court.pk))
    assert "phone" in log.changes["fields"]


def test_set_active_toggles_and_audits(office_manager):
    court = CourtFactory()
    services.set_active(actor=office_manager, court=court, is_active=False)
    court.refresh_from_db()
    assert court.is_active is False
    assert AuditLog.objects.filter(action=AuditAction.COURT_DEACTIVATED).exists()
    # idempotent
    services.set_active(actor=office_manager, court=court, is_active=False)
    assert AuditLog.objects.filter(action=AuditAction.COURT_DEACTIVATED).count() == 1


def test_court_not_deletable_in_admin():
    from courts.admin import CourtAdmin

    assert CourtAdmin(Court, None).has_delete_permission(None) is False
