import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError

from core.permissions.capabilities import GROUPS

pytestmark = pytest.mark.django_db


def test_creates_all_groups():
    Group.objects.all().delete()
    call_command("sync_roles", verbosity=0)
    assert set(Group.objects.values_list("name", flat=True)) >= set(GROUPS)


def test_office_manager_gets_expected_permissions():
    call_command("sync_roles", verbosity=0)
    om = Group.objects.get(name="office_manager")
    codenames = set(om.permissions.values_list("codename", flat=True))
    assert {"issue_temp_password", "view_auditlog", "view_user", "change_group"} <= codenames


def test_is_idempotent_and_check_passes_after_sync():
    call_command("sync_roles", verbosity=0)
    # --check must not raise when already in sync
    call_command("sync_roles", "--check", verbosity=0)


def test_check_detects_drift():
    call_command("sync_roles", verbosity=0)
    om = Group.objects.get(name="office_manager")
    om.permissions.add(Permission.objects.get(codename="delete_user"))
    with pytest.raises(CommandError):
        call_command("sync_roles", "--check", verbosity=0)


def test_removes_unexpected_permissions_on_sync():
    call_command("sync_roles", verbosity=0)
    lawyer = Group.objects.get(name="lawyer")
    lawyer.permissions.add(Permission.objects.get(codename="view_auditlog"))
    call_command("sync_roles", verbosity=0)
    assert not lawyer.permissions.exists()
