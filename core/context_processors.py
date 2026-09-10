"""Template context: permission-filtered navigation + app metadata."""

from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from core.navigation import NAV, NavItem
from core.permissions.capabilities import Capability, can, capabilities_for


def _resolve(item: NavItem, user) -> dict | None:
    if item.capability and not can(user, item.capability):
        return None

    children = [c for c in (_resolve(ch, user) for ch in item.children) if c]
    if item.children and not children:
        return None

    url = None
    if item.url_name and not item.disabled:
        try:
            url = reverse(item.url_name)
        except NoReverseMatch:
            url = None

    return {
        "label": item.label,
        "url": url,
        "url_name": item.url_name,
        "icon": item.icon,
        "disabled": item.disabled or (url is None and not children),
        "children": children,
    }


def navigation(request) -> dict:
    user = getattr(request, "user", None)
    caps = capabilities_for(user)
    items = [i for i in (_resolve(n, user) for n in NAV) if i]
    return {
        "nav_items": items,
        "user_capabilities": caps,
        "unread_notification_count": _unread_notifications(user, caps),
    }


def _unread_notifications(user, caps) -> int:
    """One indexed COUNT for the navigation badge (docs/adr/0035 §5). Served by
    the ``(recipient, read_at)`` index; skipped entirely for anonymous users."""
    if not user or not getattr(user, "is_authenticated", False):
        return 0
    if Capability.NOTIFICATIONS_VIEW not in caps:
        return 0
    from notifications.selectors import unread_count

    return unread_count(user)


def app_meta(request) -> dict:
    return {
        "APP_NAME": "قِسطاس",
        "APP_TAGLINE": "إدارة قانونية أكثر تنظيمًا",
        "DEBUG": settings.DEBUG,
    }
