import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


def test_404_is_themed_for_authenticated_user(client, user):
    client.force_login(user)
    resp = client.get("/no-such-page/")
    assert resp.status_code == 404
    body = resp.content.decode()
    assert "الصفحة غير موجودة" in body
    assert 'dir="rtl"' in body


def test_anonymous_unknown_url_still_404(client):
    # LoginRequiredMiddleware guards resolved views only, not missing URLs.
    assert client.get("/no-such-page/").status_code == 404


def test_403_page_is_themed(client, lawyer):
    # A lawyer lacks settings.view -> CapabilityRequiredMixin raises -> handler403.
    client.force_login(lawyer)
    resp = client.get("/settings/")
    assert resp.status_code == 403
    assert "غير مصرّح" in resp.content.decode()


def test_office_manager_can_open_settings(client, office_manager):
    client.force_login(office_manager)
    assert client.get("/settings/").status_code == 200


@override_settings(DEBUG=False)
def test_styleguide_404_in_production(client, office_manager):
    client.force_login(office_manager)
    assert client.get("/styleguide/").status_code == 404


@override_settings(DEBUG=True)
def test_styleguide_available_in_debug(client, office_manager):
    client.force_login(office_manager)
    assert client.get("/styleguide/").status_code == 200
