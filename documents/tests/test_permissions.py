import pytest
from django.core.management import call_command
from django.urls import reverse

from core.permissions.capabilities import Capability, can
from documents.tests.factories import DocumentFactory

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
    assert can(u, Capability.DOCUMENTS_VIEW) is view
    assert can(u, Capability.DOCUMENTS_MANAGE) is manage


def test_finance_clerk_can_view_and_download_but_not_manage(client, finance_clerk):
    d = DocumentFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("documents:detail", args=[d.pk])).status_code == 200
    assert client.get(reverse("documents:download", args=[d.pk])).status_code == 200
    assert client.get(reverse("documents:upload")).status_code == 403
    assert client.get(reverse("documents:update", args=[d.pk])).status_code == 403
    assert client.post(reverse("documents:retire", args=[d.pk])).status_code == 403


def test_sync_roles_idempotent_after_migrate(synced_roles):
    call_command("sync_roles", "--check", verbosity=0)
