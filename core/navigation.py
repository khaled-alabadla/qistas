"""
Data-driven main navigation (docs/architecture.md §11).

The sidebar is rendered from this structure and filtered through the capability
layer by ``core.context_processors.navigation``. It is a **display aid only** —
never the authorization boundary (spec §16).

Phase 1 exposes placeholders for the sections that later phases will fill.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

from core.permissions.capabilities import Capability


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str | None = None
    capability: str | None = None
    icon: str = "dot"
    children: tuple[NavItem, ...] = field(default_factory=tuple)
    disabled: bool = False  # placeholder for a not-yet-built section


NAV: tuple[NavItem, ...] = (
    NavItem(
        label=_("الرئيسية"),
        url_name="core:landing",
        capability=Capability.DASHBOARD_VIEW,
        icon="home",
    ),
    NavItem(
        label=_("العملاء"),
        capability=Capability.CLIENTS_VIEW,
        icon="users",
        children=(
            NavItem(
                label=_("جميع العملاء"),
                url_name="clients:list",
                capability=Capability.CLIENTS_VIEW,
            ),
            NavItem(
                label=_("إضافة عميل"),
                url_name="clients:create",
                capability=Capability.CLIENTS_MANAGE,
            ),
        ),
    ),
    NavItem(
        label=_("القضايا"),
        capability=Capability.CASES_VIEW,
        icon="folder",
        children=(
            NavItem(
                label=_("جميع القضايا"),
                url_name="cases:list",
                capability=Capability.CASES_VIEW,
            ),
            NavItem(
                label=_("إضافة قضية"),
                url_name="cases:create",
                capability=Capability.CASES_MANAGE,
            ),
            NavItem(
                label=_("الجلسات"),
                url_name=None,
                capability=Capability.CASES_VIEW,
                disabled=True,
            ),
        ),
    ),
    NavItem(
        label=_("الإشعارات"),
        url_name=None,
        capability=Capability.NOTIFICATIONS_VIEW,
        icon="bell",
        disabled=True,
    ),
    NavItem(
        label=_("الإعدادات"),
        url_name="core:settings",
        capability=Capability.SETTINGS_VIEW,
        icon="cog",
    ),
)
