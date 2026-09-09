import pytest
from django.core.management import call_command
from django.urls import reverse

from core.permissions.capabilities import Capability, can
from tasks.tests.factories import DeadlineFactory, TaskFactory

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
    assert can(u, Capability.TASKS_VIEW) is view
    assert can(u, Capability.TASKS_MANAGE) is manage


def test_manage_actions_forbidden_without_capability(client, finance_clerk):
    t = TaskFactory()
    d = DeadlineFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("tasks:update", args=[t.pk])).status_code == 403
    assert client.post(reverse("tasks:status", args=[t.pk]), {"status": "done"}).status_code == 403
    assert client.post(reverse("tasks:delete", args=[t.pk])).status_code == 403
    assert client.get(reverse("tasks:deadline_update", args=[d.pk])).status_code == 403


def test_view_allowed_for_finance_clerk(client, finance_clerk):
    t = TaskFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("tasks:detail", args=[t.pk])).status_code == 200
    assert client.get(reverse("tasks:deadlines")).status_code == 200


def test_sync_roles_idempotent_after_migrate(synced_roles):
    call_command("sync_roles", "--check", verbosity=0)
