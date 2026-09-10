"""Recipient-scoped read queries for the notification inbox (docs/adr/0019, 0035)."""

from __future__ import annotations

from notifications.models import Notification, NotificationCategory


def notification_list(*, user, unread_only: bool = False, category: str = ""):
    """``user``'s notifications, newest first. Always via ``for_user`` — a
    notification belongs to its recipient only."""
    qs = Notification.objects.for_user(user)
    if unread_only:
        qs = qs.unread()
    if category in NotificationCategory.values:
        qs = qs.filter(category=category)
    return qs.order_by("-created_at")


def unread_count(user) -> int:
    """Cheap indexed COUNT for the navigation badge — 0 for anonymous."""
    if not user or not user.is_authenticated:
        return 0
    return Notification.objects.for_user(user).unread().count()
