"""
The catalogue of reports (spec §43). Each entry binds a URL slug to its filter
form, its builder, and — critically — **the domain capability that gates its
data** (spec Phase 10 §6). The Reports index and every report view read the
capability from here; there is no separate "reports.view = see everything".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

from core.permissions.capabilities import Capability
from reports import forms, selectors


@dataclass(frozen=True)
class Report:
    slug: str
    label: str
    description: str
    group: str  # "general" | "financial" — display grouping on the index
    capability: str
    form_class: type
    builder: Callable
    # Financial exports and client/case listings are audited on export
    # (spec Phase 10 §17, ADR-0020).
    audit_export: bool = True

    @property
    def is_financial(self) -> bool:
        return self.group == "financial"


_REGISTRY: dict[str, Report] = {}


def _add(report: Report) -> None:
    _REGISTRY[report.slug] = report


_add(
    Report(
        slug="cases",
        label=_("تقرير القضايا"),
        description=_("القضايا حسب الحالة والنوع والمحامي والمحكمة والأولوية وتاريخ الفتح."),
        group="general",
        capability=Capability.CASES_VIEW,
        form_class=forms.CaseReportForm,
        builder=selectors.build_case_report,
    )
)
_add(
    Report(
        slug="clients",
        label=_("تقرير العملاء"),
        description=_("العملاء حسب النوع والحالة، ومن لديه قضايا نشطة."),
        group="general",
        capability=Capability.CLIENTS_VIEW,
        form_class=forms.ClientReportForm,
        builder=selectors.build_client_report,
    )
)
_add(
    Report(
        slug="hearings",
        label=_("تقرير الجلسات"),
        description=_("الجلسات حسب الحالة والمحكمة والمحامي ونطاق التاريخ."),
        group="general",
        capability=Capability.HEARINGS_VIEW,
        form_class=forms.HearingReportForm,
        builder=selectors.build_hearing_report,
    )
)
_add(
    Report(
        slug="tasks",
        label=_("تقرير المهام"),
        description=_("المهام حسب الحالة والموظف والأولوية، والمتأخرة منها."),
        group="general",
        capability=Capability.TASKS_VIEW,
        form_class=forms.TaskReportForm,
        builder=selectors.build_task_report,
    )
)
_add(
    Report(
        slug="deadlines",
        label=_("تقرير المواعيد النهائية"),
        description=_("المواعيد النهائية الإجرائية حسب الحالة، والفائت والقادم منها."),
        group="general",
        capability=Capability.TASKS_VIEW,
        form_class=forms.DeadlineReportForm,
        builder=selectors.build_deadline_report,
    )
)
_add(
    Report(
        slug="revenue",
        label=_("تقرير الإيرادات"),
        description=_("الفواتير الصادرة خلال فترة، وإجماليها لكل عملة."),
        group="financial",
        capability=Capability.FINANCE_VIEW,
        form_class=forms.RevenueReportForm,
        builder=selectors.build_revenue_report,
    )
)
_add(
    Report(
        slug="payments",
        label=_("تقرير المدفوعات"),
        description=_("الدفعات المستلمة خلال فترة، صافية بعد الاسترجاعات، لكل عملة وطريقة."),
        group="financial",
        capability=Capability.FINANCE_VIEW,
        form_class=forms.PaymentReportForm,
        builder=selectors.build_payment_report,
    )
)
_add(
    Report(
        slug="outstanding",
        label=_("تقرير الفواتير المستحقة"),
        description=_("الفواتير المفتوحة وأعمارها، لكل عملة."),
        group="financial",
        capability=Capability.FINANCE_VIEW,
        form_class=forms.OutstandingReportForm,
        builder=selectors.build_outstanding_report,
    )
)
_add(
    Report(
        slug="expenses",
        label=_("تقرير المصروفات"),
        description=_("المصروفات خلال فترة حسب التصنيف، لكل عملة."),
        group="financial",
        capability=Capability.FINANCE_VIEW,
        form_class=forms.ExpenseReportForm,
        builder=selectors.build_expense_report,
    )
)
_add(
    Report(
        slug="case-financials",
        label=_("الأداء المالي للقضايا"),
        description=_("لكل قضية: ما فُوتر، وما حُصّل، والمتبقي، والمصروفات — لكل عملة على حدة."),
        group="financial",
        capability=Capability.FINANCE_VIEW,
        form_class=forms.CaseFinancialsReportForm,
        builder=selectors.build_case_financials_report,
    )
)


def all_reports() -> list[Report]:
    return list(_REGISTRY.values())


def get_report(slug: str) -> Report | None:
    return _REGISTRY.get(slug)


def visible_reports(user) -> list[Report]:
    """Reports whose gating capability ``user`` holds (spec Phase 10 §6)."""
    from core.permissions.capabilities import can

    return [r for r in _REGISTRY.values() if can(user, r.capability)]
