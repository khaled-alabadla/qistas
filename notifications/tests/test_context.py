from __future__ import annotations

import pytest
from django.urls import reverse

from notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def test_badge_count_is_per_user(client, user, user_factory):
    NotificationFactory(recipient=user)
    NotificationFactory(recipient=user)
    read = NotificationFactory(recipient=user)
    read.mark_read()
    NotificationFactory(recipient=user_factory())  # someone else's

    client.force_login(user)
    resp = client.get(reverse("core:landing"))
    assert resp.context["unread_notification_count"] == 2


def test_badge_is_zero_for_anonymous(client):
    resp = client.get(reverse("accounts:login"))
    assert resp.context["unread_notification_count"] == 0


def test_navigation_link_is_live(client, user):
    client.force_login(user)
    resp = client.get(reverse("core:landing"))
    labels = [i["url_name"] for i in resp.context["nav_items"]]
    assert "notifications:list" in labels


def test_badge_is_a_single_count_query(user, django_assert_num_queries):
    from core.context_processors import _unread_notifications
    from core.permissions.capabilities import capabilities_for

    for _ in range(10):
        NotificationFactory(recipient=user)
    caps = capabilities_for(user)
    # the badge adds exactly one COUNT regardless of how many notifications exist
    with django_assert_num_queries(1):
        assert _unread_notifications(user, caps) == 10
