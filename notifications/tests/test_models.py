from __future__ import annotations

import pytest
from django.db import IntegrityError

from notifications.models import Notification, NotificationCategory
from notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def test_defaults_to_unread():
    n = NotificationFactory()
    assert n.read_at is None
    assert n.is_unread is True


def test_mark_read_is_idempotent():
    n = NotificationFactory()
    assert n.mark_read() is True
    assert n.read_at is not None
    first = n.read_at
    assert n.mark_read() is False
    n.refresh_from_db()
    assert n.read_at == first


def test_unique_recipient_dedupe_key(user):
    NotificationFactory(recipient=user, dedupe_key="k1")
    with pytest.raises(IntegrityError):
        NotificationFactory(recipient=user, dedupe_key="k1")


def test_same_dedupe_key_different_recipient_is_allowed(user, user_factory):
    other = user_factory()
    NotificationFactory(recipient=user, dedupe_key="shared")
    NotificationFactory(recipient=other, dedupe_key="shared")  # no error
    assert Notification.objects.filter(dedupe_key="shared").count() == 2


def test_for_user_scopes_to_recipient(user, user_factory):
    mine = NotificationFactory(recipient=user)
    NotificationFactory(recipient=user_factory())
    rows = list(Notification.objects.for_user(user))
    assert rows == [mine]


def test_for_user_anonymous_is_empty(client):
    from django.contrib.auth.models import AnonymousUser

    NotificationFactory()
    assert not Notification.objects.for_user(AnonymousUser()).exists()


def test_unread_filter(user):
    a = NotificationFactory(recipient=user)
    b = NotificationFactory(recipient=user)
    b.mark_read()
    assert list(Notification.objects.for_user(user).unread()) == [a]
    assert list(Notification.objects.for_user(user).read()) == [b]


def test_category_choices_closed():
    assert set(NotificationCategory.values) == {
        "hearing_upcoming",
        "task_overdue",
        "deadline_approaching",
        "invoice_overdue",
        "contract_expiring",
    }
