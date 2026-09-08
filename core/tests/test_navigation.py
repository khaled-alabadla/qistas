import pytest

pytestmark = pytest.mark.django_db


def test_nav_shows_settings_for_office_manager(client, office_manager):
    client.force_login(office_manager)
    html = client.get("/").content.decode()
    assert "الإعدادات" in html


def test_nav_hides_settings_for_lawyer(client, lawyer):
    client.force_login(lawyer)
    html = client.get("/").content.decode()
    assert "الإعدادات" not in html


def test_context_processor_exposes_capabilities(client, office_manager):
    client.force_login(office_manager)
    resp = client.get("/")
    assert "users.manage" in resp.context["user_capabilities"]
    assert "settings.view" in resp.context["user_capabilities"]


def test_nav_always_shows_home(client, lawyer):
    client.force_login(lawyer)
    html = client.get("/").content.decode()
    assert "الرئيسية" in html
