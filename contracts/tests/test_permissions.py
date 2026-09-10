import pytest
from django.core.management import call_command
from django.urls import reverse

from contracts.models import ContractStatus
from contracts.tests.factories import ContractFactory
from core.permissions.capabilities import Capability, can

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,view,manage",
    [
        ("office_manager", True, True),
        ("lawyer", True, True),
        ("admin_clerk", True, True),
        ("paralegal", True, False),  # paralegal is VIEW-ONLY for contracts (ADR-0031)
        ("finance_clerk", True, False),
    ],
)
def test_capability_matrix(role_user, role, view, manage):
    u = role_user(role)
    assert can(u, Capability.CONTRACTS_VIEW) is view
    assert can(u, Capability.CONTRACTS_MANAGE) is manage


def test_manage_actions_forbidden_without_capability(client, paralegal):
    c = ContractFactory(status=ContractStatus.DRAFT)
    client.force_login(paralegal)
    assert client.get(reverse("contracts:create")).status_code == 403
    assert client.get(reverse("contracts:update", args=[c.pk])).status_code == 403
    assert (
        client.post(reverse("contracts:status", args=[c.pk]), {"status": "active"}).status_code
        == 403
    )


def test_view_allowed_for_paralegal_and_finance_clerk(client, role_user):
    c = ContractFactory()
    for role in ("paralegal", "finance_clerk"):
        client.force_login(role_user(role))
        assert client.get(reverse("contracts:list")).status_code == 200
        assert client.get(reverse("contracts:detail", args=[c.pk])).status_code == 200


def test_sync_roles_idempotent_after_migrate(synced_roles):
    call_command("sync_roles", "--check", verbosity=0)
