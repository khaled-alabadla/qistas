import pytest
from django.core.management import call_command

from core.permissions.capabilities import Capability, can

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,view,manage",
    [
        ("office_manager", True, True),
        ("lawyer", True, False),
        ("paralegal", True, False),
        ("admin_clerk", True, False),
        ("finance_clerk", True, False),
    ],
)
def test_capability_matrix(role_user, role, view, manage):
    u = role_user(role)
    assert can(u, Capability.COURTS_VIEW) is view
    assert can(u, Capability.COURTS_MANAGE) is manage


def test_sync_roles_idempotent_after_migrate(synced_roles):
    call_command("sync_roles", "--check", verbosity=0)
