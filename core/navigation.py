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
                url_name="hearings:list",
                capability=Capability.HEARINGS_VIEW,
            ),
            NavItem(
                label=_("المحاكم"),
                url_name="courts:list",
                capability=Capability.COURTS_VIEW,
            ),
        ),
    ),
    NavItem(
        label=_("المكتب"),
        capability=Capability.AGENDA_VIEW,
        icon="calendar",
        children=(
            NavItem(
                label=_("المهام"),
                url_name="tasks:list",
                capability=Capability.TASKS_VIEW,
            ),
            NavItem(
                label=_("المواعيد النهائية"),
                url_name="tasks:deadlines",
                capability=Capability.TASKS_VIEW,
            ),
            NavItem(
                label=_("التقويم"),
                url_name="agenda:month",
                capability=Capability.AGENDA_VIEW,
            ),
        ),
    ),
    NavItem(
        label=_("المستندات والعقود"),
        capability=Capability.DOCUMENTS_VIEW,
        icon="file-text",
        children=(
            NavItem(
                label=_("المستندات"),
                url_name="documents:list",
                capability=Capability.DOCUMENTS_VIEW,
            ),
            NavItem(
                label=_("العقود"),
                url_name="contracts:list",
                capability=Capability.CONTRACTS_VIEW,
            ),
            NavItem(
                label=_("عقد جديد"),
                url_name="contracts:create",
                capability=Capability.CONTRACTS_MANAGE,
            ),
        ),
    ),
    NavItem(
        label=_("المالية"),
        capability=Capability.FINANCE_VIEW,
        icon="wallet",
        children=(
            NavItem(
                label=_("الفواتير"),
                url_name="finance:invoice_list",
                capability=Capability.FINANCE_VIEW,
            ),
            NavItem(
                label=_("المدفوعات"),
                url_name="finance:payment_list",
                capability=Capability.FINANCE_VIEW,
            ),
            NavItem(
                label=_("المصروفات"),
                url_name="finance:expense_list",
                capability=Capability.FINANCE_VIEW,
            ),
            NavItem(
                label=_("رسوم القضايا"),
                url_name="finance:fee_agreement_list",
                capability=Capability.FINANCE_VIEW,
            ),
        ),
    ),
    NavItem(
        label=_("التقارير"),
        url_name="reports:index",
        capability=Capability.REPORTS_VIEW,
        icon="chart",
    ),
    NavItem(
        label=_("الإشعارات"),
        url_name="notifications:list",
        capability=Capability.NOTIFICATIONS_VIEW,
        icon="bell",
    ),
    NavItem(
        label=_("الإعدادات"),
        url_name="core:settings",
        capability=Capability.SETTINGS_VIEW,
        icon="cog",
    ),
)
