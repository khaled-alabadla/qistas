"""
Centralized capability layer (docs/adr/0007).

Django **Groups** are the source of truth for authorization; a user may belong
to several. This module is the ONE place that maps groups to named capabilities.
`can(user, capability)` resolves over the union of the user's groups.

Phase 1 has no domain entities, so capabilities are navigation-level only. Each
later phase adds its capabilities here and wires views/templates to `can()`.
The `sync_roles` command keeps Django permissions aligned with these groups.
"""

from __future__ import annotations

from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


class Group(TextChoices):
    OFFICE_MANAGER = "office_manager", _("مدير المكتب")
    LAWYER = "lawyer", _("محامٍ")
    PARALEGAL = "paralegal", _("مساعد محامٍ")
    ADMIN_CLERK = "admin_clerk", _("موظف إداري")
    FINANCE_CLERK = "finance_clerk", _("موظف مالي")


GROUPS: tuple[str, ...] = tuple(g.value for g in Group)


class Capability(TextChoices):
    """Named permissions checked in views/templates. Values are stable strings."""

    DASHBOARD_VIEW = "dashboard.view", _("عرض الرئيسية")
    NOTIFICATIONS_VIEW = "notifications.view", _("عرض الإشعارات")
    SETTINGS_VIEW = "settings.view", _("عرض الإعدادات")
    AUDIT_VIEW = "audit.view", _("عرض سجل التدقيق")
    USERS_MANAGE = "users.manage", _("إدارة المستخدمين")


# group -> capabilities it grants. Fixed in code for v1 (docs/adr/0007);
# only group *membership* is admin-editable.
_ALL_STAFF = {Capability.DASHBOARD_VIEW, Capability.NOTIFICATIONS_VIEW}

GROUP_CAPABILITIES: dict[str, set[str]] = {
    Group.OFFICE_MANAGER: {
        Capability.DASHBOARD_VIEW,
        Capability.NOTIFICATIONS_VIEW,
        Capability.SETTINGS_VIEW,
        Capability.AUDIT_VIEW,
        Capability.USERS_MANAGE,
    },
    Group.LAWYER: set(_ALL_STAFF),
    Group.PARALEGAL: set(_ALL_STAFF),
    Group.ADMIN_CLERK: set(_ALL_STAFF),
    Group.FINANCE_CLERK: set(_ALL_STAFF),
}
# normalise to plain str
GROUP_CAPABILITIES = {str(k): {str(c) for c in v} for k, v in GROUP_CAPABILITIES.items()}


def capabilities_for(user) -> frozenset[str]:
    """Union of capabilities across the user's groups. Superusers get all."""
    if not user or not user.is_authenticated:
        return frozenset()
    if user.is_superuser:
        return frozenset(str(c) for c in Capability)
    caps: set[str] = set()
    for group_name in user.groups.values_list("name", flat=True):
        caps |= GROUP_CAPABILITIES.get(group_name, set())
    return frozenset(caps)


def can(user, capability: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return str(capability) in capabilities_for(user)
