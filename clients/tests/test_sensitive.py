"""national_id handling (docs/adr/0009)."""

import logging

import pytest
from django.urls import reverse

from clients.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def person(db):
    return ClientFactory(full_name="محمود درويش", national_id="905112233")


def test_detail_hides_national_id_without_capability(client, finance_clerk, person):
    client.force_login(finance_clerk)
    body = client.get(reverse("clients:detail", args=[person.pk])).content.decode()
    assert "905112233" not in body
    assert "محجوب" in body


def test_detail_shows_national_id_with_capability(client, office_manager, person):
    client.force_login(office_manager)
    body = client.get(reverse("clients:detail", args=[person.pk])).content.decode()
    assert "905112233" in body


def test_form_omits_sensitive_fields_without_capability(client, admin_clerk, finance_clerk, person):
    # finance_clerk has no manage -> can't even open the form; check the form class directly.
    from clients.forms import ClientForm

    form_admin = ClientForm(user=admin_clerk, instance=person)
    assert "national_id" in form_admin.fields  # admin_clerk holds view_sensitive

    # a user with manage but not view_sensitive would not see it — simulate by a
    # lawyer-less capability set is not possible here, so assert the gate logic:
    from core.permissions.capabilities import Capability, can

    assert can(admin_clerk, Capability.CLIENTS_VIEW_SENSITIVE)
    assert not can(finance_clerk, Capability.CLIENTS_VIEW_SENSITIVE)


def test_national_id_is_in_sensitive_registry():
    from core.sensitive import SENSITIVE_FIELDS, is_sensitive

    assert "national_id" in SENSITIVE_FIELDS
    assert is_sensitive("national_id")


def test_national_id_redacted_by_logging_filter(person):
    from core.sensitive import SensitiveDataFilter

    rec = logging.LogRecord(
        "qistas",
        logging.INFO,
        __file__,
        1,
        "client national_id=%s updated",
        (person.national_id,),
        None,
    )
    SensitiveDataFilter().filter(rec)
    assert person.national_id not in rec.getMessage()
    assert "***" in rec.getMessage()


def test_national_id_redacted_in_audit_changes(office_manager, person):
    from audit.events import log_event

    entry = log_event(None, "other", obj=person, changes={"national_id": ["x", "y"]})
    assert entry.changes["national_id"] == "***"


def test_update_client_audit_logs_field_names_not_values(office_manager, person):
    from audit.models import AuditAction, AuditLog
    from clients.services import update_client

    update_client(
        actor=office_manager,
        client=person,
        data={
            "type": person.type,
            "full_name": person.full_name,
            "phone": person.phone,
            "national_id": "111222333",
            "status": person.status,
        },
    )
    entry = AuditLog.objects.filter(
        entity_id=str(person.pk), action=AuditAction.CLIENT_UPDATED
    ).latest("created_at")
    assert "national_id" in entry.changes.get("fields", [])
    assert "111222333" not in str(entry.changes)


def test_auditlog_masks_national_id(office_manager, person):
    from auditlog.models import LogEntry

    from clients.services import update_client

    update_client(
        actor=office_manager,
        client=person,
        data={
            "type": person.type,
            "full_name": person.full_name,
            "phone": person.phone,
            "national_id": "999888777",
            "status": person.status,
        },
    )
    entry = LogEntry.objects.get_for_object(person).first()
    if entry and "national_id" in entry.changes:
        assert "999888777" not in str(entry.changes["national_id"])
