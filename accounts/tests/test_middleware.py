import time

import pytest
from django.test import override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_must_change_password_redirects(client, user_factory):
    u = user_factory()
    u.must_change_password = True
    u.save()
    client.force_login(u)
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("accounts:password_change")


def test_must_change_password_allows_the_change_page(client, user_factory):
    u = user_factory()
    u.must_change_password = True
    u.save()
    client.force_login(u)
    assert client.get(reverse("accounts:password_change")).status_code == 200


@override_settings(IDLE_TIMEOUT_SECONDS=1)
def test_idle_timeout_logs_out(client, user):
    client.force_login(user)
    session = client.session
    session["_last_activity"] = time.time() - 5
    session.save()
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("accounts:login")
    assert "_auth_user_id" not in client.session


def test_login_required_middleware_guards_resolved_views_only(client):
    # unresolved -> 404, resolved+protected -> redirect
    assert client.get("/definitely-not-a-route/").status_code == 404
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_healthz_is_public(client):
    assert client.get("/healthz/").status_code == 200
