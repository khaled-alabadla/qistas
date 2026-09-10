from __future__ import annotations

import pytest
from django.urls import reverse

from notifications.models import Notification
from notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def test_anonymous_is_redirected(client):
    resp = client.get(reverse("notifications:list"))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


def test_list_shows_only_own_notifications(client, user, user_factory):
    mine = NotificationFactory(recipient=user, title="لي")
    NotificationFactory(recipient=user_factory(), title="لغيري")
    client.force_login(user)

    resp = client.get(reverse("notifications:list"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert mine.title in body
    assert "لغيري" not in body


def test_unread_filter(client, user):
    a = NotificationFactory(recipient=user)
    b = NotificationFactory(recipient=user)
    b.mark_read()
    client.force_login(user)

    resp = client.get(reverse("notifications:list"), {"filter": "unread"})
    body = resp.content.decode()
    assert a.title in body
    assert b.title not in body


def test_mark_one_read(client, user):
    n = NotificationFactory(recipient=user)
    client.force_login(user)

    resp = client.post(reverse("notifications:mark_read", args=[n.pk]))
    assert resp.status_code == 302
    n.refresh_from_db()
    assert n.read_at is not None


def test_mark_read_get_is_rejected(client, user):
    n = NotificationFactory(recipient=user)
    client.force_login(user)
    assert client.get(reverse("notifications:mark_read", args=[n.pk])).status_code == 405


def test_cannot_mark_another_users_notification(client, user, user_factory):
    victim = user_factory()
    n = NotificationFactory(recipient=victim)
    client.force_login(user)

    # scoped queryset -> silent no-op (still a redirect, never reveals the row)
    resp = client.post(reverse("notifications:mark_read", args=[n.pk]))
    assert resp.status_code == 302
    n.refresh_from_db()
    assert n.read_at is None


def test_mark_all_read(client, user, user_factory):
    other = user_factory()
    NotificationFactory(recipient=user)
    NotificationFactory(recipient=user)
    victim_n = NotificationFactory(recipient=other)
    client.force_login(user)

    client.post(reverse("notifications:mark_all_read"))
    assert not Notification.objects.for_user(user).unread().exists()
    victim_n.refresh_from_db()
    assert victim_n.read_at is None


def test_open_marks_read_and_redirects_to_target(client, user):
    n = NotificationFactory(recipient=user, url="/cases/")
    client.force_login(user)

    resp = client.get(reverse("notifications:open", args=[n.pk]))
    assert resp.status_code == 302
    assert resp["Location"] == "/cases/"
    n.refresh_from_db()
    assert n.read_at is not None


def test_open_another_users_notification_is_404(client, user, user_factory):
    n = NotificationFactory(recipient=user_factory())
    client.force_login(user)
    assert client.get(reverse("notifications:open", args=[n.pk])).status_code == 404


def test_open_rejects_offsite_url(client, user):
    n = NotificationFactory(recipient=user, url="https://evil.example/phish")
    client.force_login(user)
    resp = client.get(reverse("notifications:open", args=[n.pk]))
    assert resp["Location"] == reverse("notifications:list")


def test_mark_read_next_must_be_local(client, user):
    n = NotificationFactory(recipient=user)
    client.force_login(user)
    resp = client.post(
        reverse("notifications:mark_read", args=[n.pk]), {"next": "https://evil.example"}
    )
    assert resp["Location"] == reverse("notifications:list")
