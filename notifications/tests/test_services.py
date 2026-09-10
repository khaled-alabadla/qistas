from __future__ import annotations

import pytest

from notifications import services
from notifications.models import Notification, NotificationCategory
from notifications.services import NotificationSpec
from notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def _spec(user, key="k", **kw):
    return NotificationSpec(
        recipient_id=user.id,
        category=NotificationCategory.TASK_OVERDUE,
        title=kw.get("title", "t"),
        body=kw.get("body", "b"),
        dedupe_key=key,
        url=kw.get("url", "/"),
        entity_type="tasks.task",
        entity_id=kw.get("entity_id", "1"),
    )


def test_notify_creates_once_then_dedupes(user):
    n1, c1 = services.notify(
        recipient=user,
        category=NotificationCategory.TASK_OVERDUE,
        title="t",
        body="b",
        dedupe_key="abc",
    )
    assert c1 is True
    n2, c2 = services.notify(
        recipient=user,
        category=NotificationCategory.TASK_OVERDUE,
        title="different",
        body="b",
        dedupe_key="abc",
    )
    assert c2 is False
    assert n1.pk == n2.pk
    assert Notification.objects.filter(recipient=user).count() == 1


def test_bulk_notify_inserts_missing_only(user, user_factory):
    other = user_factory()
    created = services.bulk_notify([_spec(user, "a"), _spec(other, "a"), _spec(user, "b")])
    assert created == 3

    # re-run with an overlap + one new
    created2 = services.bulk_notify([_spec(user, "a"), _spec(user, "c")])
    assert created2 == 1
    assert Notification.objects.count() == 4


def test_bulk_notify_dedupes_within_the_batch(user):
    created = services.bulk_notify([_spec(user, "x"), _spec(user, "x")])
    assert created == 1


def test_bulk_notify_empty():
    assert services.bulk_notify([]) == 0


def test_mark_read_only_touches_own(user, user_factory):
    other = user_factory()
    mine = NotificationFactory(recipient=user)
    theirs = NotificationFactory(recipient=other)

    assert services.mark_read(user=user, notification_id=mine.pk) is True
    # tampering with someone else's id is a silent no-op, not an error
    assert services.mark_read(user=user, notification_id=theirs.pk) is False
    theirs.refresh_from_db()
    assert theirs.read_at is None


def test_mark_all_read(user, user_factory):
    other = user_factory()
    NotificationFactory(recipient=user)
    NotificationFactory(recipient=user)
    NotificationFactory(recipient=other)

    n = services.mark_all_read(user=user)
    assert n == 2
    assert not Notification.objects.for_user(user).unread().exists()
    assert Notification.objects.for_user(other).unread().count() == 1


def test_mark_all_read_when_nothing_unread(user):
    assert services.mark_all_read(user=user) == 0
