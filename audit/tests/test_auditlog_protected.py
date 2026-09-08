import pytest

from audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_instance_delete_is_blocked():
    entry = AuditLog.objects.create(action="other", object_repr="x")
    with pytest.raises(PermissionError):
        entry.delete()
    assert AuditLog.objects.filter(pk=entry.pk).exists()


def test_bulk_delete_is_blocked():
    AuditLog.objects.create(action="other", object_repr="y")
    with pytest.raises(PermissionError):
        AuditLog.objects.all().delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.update(action="tampered")


def test_actor_set_null_still_works_when_user_deleted(user_factory):
    from audit.events import log_event

    u = user_factory()
    entry = log_event(None, "other", actor=u, obj=u)
    u.delete()
    entry.refresh_from_db()
    assert entry.actor_id is None


def test_no_delete_permission_declared():
    from django.contrib.auth.models import Permission

    assert not Permission.objects.filter(
        content_type__app_label="audit",
        content_type__model="auditlog",
        codename="delete_auditlog",
    ).exists()


def test_admin_forbids_mutation(user_factory):
    from django.contrib.admin.sites import AdminSite

    from audit.admin import AuditLogAdmin

    ma = AuditLogAdmin(AuditLog, AdminSite())

    class Req:
        user = None

    assert ma.has_add_permission(Req()) is False
    assert ma.has_change_permission(Req()) is False
    assert ma.has_delete_permission(Req()) is False
