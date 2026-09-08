import pytest
from django.test import override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_axes():
    from axes.handlers.proxy import AxesProxyHandler

    AxesProxyHandler().reset_attempts()
    yield
    AxesProxyHandler().reset_attempts()


@override_settings(AXES_FAILURE_LIMIT=3)
def test_lockout_by_username_after_limit(client, user):
    url = reverse("accounts:login")
    for _ in range(3):
        client.post(url, {"username": user.email, "password": "wrong"})
    # 4th attempt — even with the correct password — is locked out.
    resp = client.post(url, {"username": user.email, "password": "correct-horse-staple-11"})
    assert resp.status_code == 429
    assert "مقفل" in resp.content.decode()


@override_settings(AXES_FAILURE_LIMIT=3)
def test_lockout_does_not_affect_other_username_same_ip(client, user_factory):
    victim = user_factory()
    other = user_factory()
    url = reverse("accounts:login")
    for _ in range(3):
        client.post(url, {"username": victim.email, "password": "wrong"})
    # A different account from the same IP still works (lockout is username-only).
    resp = client.post(url, {"username": other.email, "password": "correct-horse-staple-11"})
    assert resp.status_code == 302
    assert client.session.get("_auth_user_id") == str(other.pk)


@override_settings(AXES_FAILURE_LIMIT=3)
def test_lockout_writes_audit_event(client, user):
    from audit.models import AuditAction, AuditLog

    url = reverse("accounts:login")
    for _ in range(3):
        client.post(url, {"username": user.email, "password": "wrong"})
    client.post(url, {"username": user.email, "password": "wrong"})
    assert AuditLog.objects.filter(action=AuditAction.LOCKOUT).exists()


@override_settings(AXES_FAILURE_LIMIT=3)
def test_admin_can_unlock_by_clearing_access_attempt(client, user):
    from axes.handlers.proxy import AxesProxyHandler
    from axes.models import AccessAttempt

    url = reverse("accounts:login")
    for _ in range(3):
        client.post(url, {"username": user.email, "password": "wrong"})
    assert AxesProxyHandler.is_locked(client.request().wsgi_request, {"username": user.email})

    # An admin unlocks by deleting the AccessAttempt row (exposed in the Django
    # admin at axes/accessattempt/) or via `manage.py axes_reset_user`.
    AccessAttempt.objects.filter(username=user.email).delete()

    resp = client.post(url, {"username": user.email, "password": "correct-horse-staple-11"})
    assert resp.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)


def test_access_attempt_is_in_admin():
    from axes.models import AccessAttempt
    from django.contrib import admin

    assert AccessAttempt in admin.site._registry
