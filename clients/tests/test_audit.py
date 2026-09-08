import pytest

from audit.models import AuditAction, AuditLog
from clients.models import ClientType
from clients.services import archive_client, create_client, restore_client, update_client
from clients.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


def _events(client):
    return set(
        AuditLog.objects.filter(entity_type="clients.client", entity_id=str(client.pk)).values_list(
            "action", flat=True
        )
    )


def test_create_update_archive_restore_are_audited(office_manager):
    c = create_client(
        actor=office_manager,
        data={"type": ClientType.INDIVIDUAL, "full_name": "أحمد", "phone": "059"},
    )
    assert AuditAction.CLIENT_CREATED in _events(c)

    update_client(
        actor=office_manager,
        client=c,
        data={
            "type": c.type,
            "full_name": c.full_name,
            "phone": c.phone,
            "city": "غزة",
            "status": c.status,
        },
    )
    archive_client(actor=office_manager, client=c)
    restore_client(actor=office_manager, client=c)

    assert {
        AuditAction.CLIENT_CREATED,
        AuditAction.CLIENT_UPDATED,
        AuditAction.CLIENT_ARCHIVED,
        AuditAction.CLIENT_RESTORED,
    } <= _events(c)


def test_archive_records_status_transition(office_manager):
    c = ClientFactory()
    archive_client(actor=office_manager, client=c)
    entry = AuditLog.objects.get(
        entity_type="clients.client", entity_id=str(c.pk), action=AuditAction.CLIENT_ARCHIVED
    )
    assert entry.changes["status"] == ["active", "archived"]
    assert entry.actor == office_manager


def test_auditlog_registered_for_client():
    from auditlog.registry import auditlog

    from clients.models import Client

    assert auditlog.contains(Client)


def test_archive_is_idempotent_no_duplicate_event(office_manager):
    c = ClientFactory()
    archive_client(actor=office_manager, client=c)
    archive_client(actor=office_manager, client=c)
    assert (
        AuditLog.objects.filter(entity_id=str(c.pk), action=AuditAction.CLIENT_ARCHIVED).count()
        == 1
    )


def test_update_records_actual_changed_fields(office_manager):
    c = ClientFactory(city="نابلس", email="")
    update_client(
        actor=office_manager,
        client=c,
        data={
            "type": c.type,
            "full_name": c.full_name,
            "phone": c.phone,
            "city": "رام الله",
            "email": "x@y.ps",
            "status": c.status,
        },
    )
    entry = AuditLog.objects.get(entity_id=str(c.pk), action=AuditAction.CLIENT_UPDATED)
    assert set(entry.changes["fields"]) == {"city", "email"}


def test_update_with_no_changes_is_a_noop(office_manager):
    c = ClientFactory(city="جنين")
    update_client(
        actor=office_manager,
        client=c,
        data={
            "type": c.type,
            "full_name": c.full_name,
            "phone": c.phone,
            "city": "جنين",
            "status": c.status,
        },
    )
    assert not AuditLog.objects.filter(
        entity_id=str(c.pk), action=AuditAction.CLIENT_UPDATED
    ).exists()


def test_update_via_form_view_records_real_diff(client, office_manager):
    from django.urls import reverse

    c = ClientFactory(city="نابلس")
    client.force_login(office_manager)
    client.post(
        reverse("clients:update", args=[c.pk]),
        {
            "type": c.type,
            "full_name": c.full_name,
            "phone": c.phone,
            "city": "الخليل",
            "status": c.status,
        },
    )
    entry = AuditLog.objects.get(entity_id=str(c.pk), action=AuditAction.CLIENT_UPDATED)
    assert "city" in entry.changes["fields"]
