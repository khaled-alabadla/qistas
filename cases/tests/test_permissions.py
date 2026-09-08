import pytest
from django.core.management import call_command
from django.urls import reverse

from cases.tests.factories import CaseFactory
from core.permissions.capabilities import Capability, can

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,view,manage,confidential",
    [
        ("office_manager", True, True, True),
        ("lawyer", True, True, True),
        ("paralegal", True, True, False),
        ("admin_clerk", True, True, False),
        ("finance_clerk", True, False, False),
    ],
)
def test_capability_matrix(role_user, role, view, manage, confidential):
    u = role_user(role)
    assert can(u, Capability.CASES_VIEW) is view
    assert can(u, Capability.CASES_MANAGE) is manage
    assert can(u, Capability.CASES_VIEW_CONFIDENTIAL) is confidential


def test_edit_forbidden_without_manage(client, finance_clerk):
    c = CaseFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("cases:update", args=[c.pk])).status_code == 403
    resp = client.post(reverse("cases:status", args=[c.pk]), {"status": "in_progress"})
    assert resp.status_code == 403


def test_confidential_view_forbidden_without_capability(client, paralegal):
    c = CaseFactory()
    client.force_login(paralegal)
    assert client.get(reverse("cases:confidential", args=[c.pk])).status_code == 403


def test_confidential_view_allowed_for_lawyer(client, lawyer):
    c = CaseFactory()
    client.force_login(lawyer)
    assert client.get(reverse("cases:confidential", args=[c.pk])).status_code == 200


def test_sync_roles_idempotent_after_migrate(synced_roles):
    call_command("sync_roles", "--check", verbosity=0)
