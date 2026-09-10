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
    REPORTS_VIEW = "reports.view", _("عرض التقارير")
    NOTIFICATIONS_VIEW = "notifications.view", _("عرض الإشعارات")
    SETTINGS_VIEW = "settings.view", _("عرض الإعدادات")
    AUDIT_VIEW = "audit.view", _("عرض سجل التدقيق")
    USERS_MANAGE = "users.manage", _("إدارة المستخدمين")
    # Phase 2 — Clients
    CLIENTS_VIEW = "clients.view", _("عرض العملاء")
    CLIENTS_MANAGE = "clients.manage", _("إضافة وتعديل العملاء")
    CLIENTS_VIEW_SENSITIVE = "clients.view_sensitive", _("عرض بيانات العملاء الحساسة")
    # Phase 3 — Cases
    CASES_VIEW = "cases.view", _("عرض القضايا")
    CASES_MANAGE = "cases.manage", _("إضافة وتعديل القضايا")
    CASES_VIEW_CONFIDENTIAL = "cases.view_confidential", _("عرض الملاحظات السرية للقضايا")
    # Phase 4 — Courts, Hearings, Calendar
    COURTS_VIEW = "courts.view", _("عرض المحاكم")
    COURTS_MANAGE = "courts.manage", _("إضافة وتعديل المحاكم")
    HEARINGS_VIEW = "hearings.view", _("عرض الجلسات")
    HEARINGS_MANAGE = "hearings.manage", _("جدولة وتحديث الجلسات")
    AGENDA_VIEW = "agenda.view", _("عرض التقويم")
    # Phase 5 — Tasks + Deadlines
    TASKS_VIEW = "tasks.view", _("عرض المهام والمواعيد النهائية")
    TASKS_MANAGE = "tasks.manage", _("إضافة وتحديث المهام والمواعيد النهائية")
    # Phase 6 — Documents
    DOCUMENTS_VIEW = "documents.view", _("عرض المستندات وتنزيلها")
    DOCUMENTS_MANAGE = "documents.manage", _("رفع المستندات وتعديلها وسحبها")
    # Phase 7 — Contracts
    CONTRACTS_VIEW = "contracts.view", _("عرض العقود")
    CONTRACTS_MANAGE = "contracts.manage", _("إضافة وتعديل العقود")
    # Phase 8 — Finance
    FINANCE_VIEW = "finance.view", _("عرض السجلات المالية")
    FINANCE_MANAGE = "finance.manage", _("إدارة الفواتير والمدفوعات والمصروفات واتفاقيات الأتعاب")


# group -> capabilities it grants. Fixed in code for v1 (docs/adr/0007);
# only group *membership* is admin-editable.
# Every staff member can see the dashboard, notifications, and the client directory.
_ALL_STAFF = {
    Capability.DASHBOARD_VIEW,
    Capability.REPORTS_VIEW,
    Capability.NOTIFICATIONS_VIEW,
    Capability.CLIENTS_VIEW,
    Capability.CASES_VIEW,
    Capability.COURTS_VIEW,
    Capability.HEARINGS_VIEW,
    Capability.AGENDA_VIEW,
    Capability.TASKS_VIEW,
    Capability.DOCUMENTS_VIEW,
    Capability.CONTRACTS_VIEW,
}
# Roles that intake / represent clients and legitimately need the national ID.
_CLIENT_HANDLERS = {Capability.CLIENTS_MANAGE, Capability.CLIENTS_VIEW_SENSITIVE}
# Roles that run case files day to day (create, edit, assign, add parties/notes).
_CASE_HANDLERS = {Capability.CASES_MANAGE}
# Roles trusted with privileged legal / internal case notes (docs/adr/0008, 0009).
_CASE_CONFIDENTIAL = {Capability.CASES_VIEW_CONFIDENTIAL}
# Roles that run case logistics — the same handlers also schedule hearings (ADR-0028).
# Courts are shared reference data — only the office manager curates them (ADR-0028).
_HEARING_HANDLERS = {Capability.HEARINGS_MANAGE}
# The same case handlers own tasks + deadlines (docs/adr/0029). One capability
# pair covers both models. finance_clerk is view-only.
_TASK_HANDLERS = {Capability.TASKS_MANAGE}
# Same case handlers upload / edit / retire documents (docs/adr/0030).
# finance_clerk keeps documents.view (invoice/receipt context) but cannot manage.
_DOCUMENT_HANDLERS = {Capability.DOCUMENTS_MANAGE}
# Contracts are engagement instruments with a client — the CLIENT-handler set
# manages them (office_manager / lawyer / admin_clerk), NOT the case-handler set:
# paralegal is view-only here, finance_clerk keeps contracts.view (billing
# context) but cannot manage (docs/adr/0031).
_CONTRACT_HANDLERS = {Capability.CONTRACTS_MANAGE}
# Finance is NOT all-staff — it is permission-controlled (spec §98). `finance.view`
# reaches the office manager, the finance clerk, and the lawyers / admin clerks who
# need billing context for their matters; **paralegal has no finance access** (§12
# — "limited access to assigned work"). `finance.manage` (fee agreements, invoice
# draft/issue/cancel, payments, reversals, credit notes, expenses) is the finance
# clerk + office manager only (docs/adr/0032).
_FINANCE_VIEWERS = {Capability.FINANCE_VIEW}
_FINANCE_HANDLERS = {Capability.FINANCE_VIEW, Capability.FINANCE_MANAGE}

GROUP_CAPABILITIES: dict[str, set[str]] = {
    Group.OFFICE_MANAGER: {
        Capability.DASHBOARD_VIEW,
        Capability.REPORTS_VIEW,
        Capability.NOTIFICATIONS_VIEW,
        Capability.SETTINGS_VIEW,
        Capability.AUDIT_VIEW,
        Capability.USERS_MANAGE,
        Capability.CLIENTS_VIEW,
        Capability.CLIENTS_MANAGE,
        Capability.CLIENTS_VIEW_SENSITIVE,
        Capability.CASES_VIEW,
        Capability.CASES_MANAGE,
        Capability.CASES_VIEW_CONFIDENTIAL,
        Capability.COURTS_VIEW,
        Capability.COURTS_MANAGE,
        Capability.HEARINGS_VIEW,
        Capability.HEARINGS_MANAGE,
        Capability.AGENDA_VIEW,
        Capability.TASKS_VIEW,
        Capability.TASKS_MANAGE,
        Capability.DOCUMENTS_VIEW,
        Capability.DOCUMENTS_MANAGE,
        Capability.CONTRACTS_VIEW,
        Capability.CONTRACTS_MANAGE,
        Capability.FINANCE_VIEW,
        Capability.FINANCE_MANAGE,
    },
    Group.LAWYER: _ALL_STAFF
    | _CLIENT_HANDLERS
    | _CASE_HANDLERS
    | _CASE_CONFIDENTIAL
    | _HEARING_HANDLERS
    | _TASK_HANDLERS
    | _DOCUMENT_HANDLERS
    | _CONTRACT_HANDLERS
    | _FINANCE_VIEWERS,
    Group.PARALEGAL: _ALL_STAFF
    | _CASE_HANDLERS
    | _HEARING_HANDLERS
    | _TASK_HANDLERS
    | _DOCUMENT_HANDLERS,
    Group.ADMIN_CLERK: _ALL_STAFF
    | _CLIENT_HANDLERS
    | _CASE_HANDLERS
    | _HEARING_HANDLERS
    | _TASK_HANDLERS
    | _DOCUMENT_HANDLERS
    | _CONTRACT_HANDLERS
    | _FINANCE_VIEWERS,
    Group.FINANCE_CLERK: set(_ALL_STAFF) | _FINANCE_HANDLERS,
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


def groups_with_capability(capability: str) -> frozenset[str]:
    """Every group name whose capability set grants ``capability``. Used by the
    notification reminder scan to resolve recipients (docs/adr/0035 §3)."""
    cap = str(capability)
    return frozenset(g for g, caps in GROUP_CAPABILITIES.items() if cap in caps)


def users_with_capability(capability: str):
    """Active users who hold ``capability`` through group membership.

    A defence-in-depth backstop for notification generation: the recipient list
    is intersected with this before any row is created, so e.g. a finance
    notification can never reach a paralegal (docs/adr/0032, 0035 §3).
    Superusers are intentionally **not** included — the reminder scan targets
    real staff inboxes, not the break-glass account.
    """
    from django.contrib.auth import get_user_model

    return (
        get_user_model()
        ._default_manager.filter(
            is_active=True, groups__name__in=list(groups_with_capability(capability))
        )
        .distinct()
    )
