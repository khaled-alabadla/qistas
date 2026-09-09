import pytest
from django.core.management import call_command
from django.urls import reverse

from core.permissions.capabilities import Capability, can
from hearings.tests.factories import HearingFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,view,manage",
    [
        ("office_manager", True, True),
        ("lawyer", True, True),
        ("paralegal", True, True),
        ("admin_clerk", True, True),
        ("finance_clerk", True, False),
    ],
)
def test_capability_matrix(role_user, role, view, manage):
    u = role_user(role)
    assert can(u, Capability.HEARINGS_VIEW) is view
    assert can(u, Capability.HEARINGS_MANAGE) is manage


def test_schedule_forbidden_without_manage(client, finance_clerk):
    client.force_login(finance_clerk)
    assert client.get(reverse("hearings:schedule")).status_code == 403


def test_lifecycle_actions_forbidden_without_manage(client, finance_clerk):
    h = HearingFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("hearings:update", args=[h.pk])).status_code == 403
    assert client.post(reverse("hearings:cancel", args=[h.pk])).status_code == 403


def test_sync_roles_idempotent_after_migrate(synced_roles):
    call_command("sync_roles", "--check", verbosity=0)
