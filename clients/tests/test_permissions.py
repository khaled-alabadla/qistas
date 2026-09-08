"""Capability-gate matrix for client views (docs/adr/0007, 0008)."""

import pytest
from django.urls import reverse

from clients.models import ClientStatus, ClientType
from clients.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db

VIEW_ROLES = ["office_manager", "lawyer", "paralegal", "admin_clerk", "finance_clerk"]
MANAGE_ROLES = ["office_manager", "lawyer", "admin_clerk"]
NO_MANAGE_ROLES = ["paralegal", "finance_clerk"]


@pytest.mark.parametrize("role", VIEW_ROLES)
def test_every_staff_role_can_view_list_and_detail(client, role_user, role):
    c = ClientFactory()
    client.force_login(role_user(role))
    assert client.get(reverse("clients:list")).status_code == 200
    assert client.get(reverse("clients:detail", args=[c.pk])).status_code == 200


@pytest.mark.parametrize("role", MANAGE_ROLES)
def test_manage_roles_can_open_create(client, role_user, role):
    client.force_login(role_user(role))
    assert client.get(reverse("clients:create")).status_code == 200


@pytest.mark.parametrize("role", NO_MANAGE_ROLES)
def test_non_manage_roles_get_403_on_write_views(client, role_user, role):
    c = ClientFactory(status=ClientStatus.ACTIVE)
    client.force_login(role_user(role))
    assert client.get(reverse("clients:create")).status_code == 403
    assert client.get(reverse("clients:update", args=[c.pk])).status_code == 403
    assert client.get(reverse("clients:archive_confirm", args=[c.pk])).status_code == 403
    assert client.post(reverse("clients:archive", args=[c.pk])).status_code == 403
    c.refresh_from_db()
    assert c.status == ClientStatus.ACTIVE


@pytest.mark.parametrize("role", NO_MANAGE_ROLES)
def test_non_manage_role_post_create_is_403(client, role_user, role):
    from clients.models import Client

    client.force_login(role_user(role))
    resp = client.post(
        reverse("clients:create"),
        {"type": ClientType.INDIVIDUAL, "full_name": "x", "phone": "0", "status": "active"},
    )
    assert resp.status_code == 403
    assert not Client.objects.exists()


def test_anonymous_redirected_to_login(client):
    c = ClientFactory()
    for name, args in [
        ("clients:list", []),
        ("clients:create", []),
        ("clients:detail", [c.pk]),
        ("clients:update", [c.pk]),
    ]:
        resp = client.get(reverse(name, args=args))
        assert resp.status_code == 302
        assert reverse("accounts:login") in resp["Location"]
