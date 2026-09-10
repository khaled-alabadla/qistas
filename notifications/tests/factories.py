from __future__ import annotations

import factory

from core.tests.factories import UserFactory
from notifications.models import Notification, NotificationCategory


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    recipient = factory.SubFactory(UserFactory)
    category = NotificationCategory.HEARING_UPCOMING
    title = factory.Sequence(lambda n: f"إشعار {n}")
    body = factory.Sequence(lambda n: f"نص الإشعار {n}")
    url = "/"
    dedupe_key = factory.Sequence(lambda n: f"test:{n}")
