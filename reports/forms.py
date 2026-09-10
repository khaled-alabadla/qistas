"""
Report filter forms (spec §44). Every field is **optional** — a report opens
with sensible defaults and no filters. All validation is server-side; the forms
only ever expose bounded ``ChoiceField`` / ``ModelChoiceField`` options, never a
free-form field name or ORM expression (spec Phase 10 §7).

FK pickers are scoped to what the requesting user may see.
"""

from __future__ import annotations

import datetime as dt

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from cases.models import CasePriority, CaseStatus, CaseType
from clients.models import ClientStatus, ClientType
from contracts.models import Currency
from core.forms import scoped_case_queryset, scoped_client_queryset
from finance.models import ExpenseCategory, PaymentMethod
from hearings.models import HearingStatus
from tasks.models import DeadlineStatus, TaskStatus

User = get_user_model()

_DEFAULT_DAYS_BACK = 90


class _DateInput(forms.DateInput):
    input_type = "date"


def _staff_queryset():
    return User.objects.filter(is_active=True).order_by("first_name", "last_name", "email")


class BaseReportForm(forms.Form):
    """Date-range scaffold shared by most reports. Subclasses set
    ``date_field_label`` and add their own filters. ``apply_default_window``
    controls whether an unbound form pre-fills the last 90 days."""

    date_field_label = _("التاريخ")
    apply_default_window = True
    default_days_back = _DEFAULT_DAYS_BACK
    default_days_forward = 0

    date_from = forms.DateField(label=_("من تاريخ"), required=False, widget=_DateInput)
    date_to = forms.DateField(label=_("إلى تاريخ"), required=False, widget=_DateInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["date_from"].label = _("من تاريخ (%(f)s)") % {"f": self.date_field_label}
        self.fields["date_to"].label = _("إلى تاريخ (%(f)s)") % {"f": self.date_field_label}
        if not self.is_bound and self.apply_default_window:
            back, fwd = self._default_bounds()
            self.fields["date_from"].initial = back
            self.fields["date_to"].initial = fwd

    def _default_bounds(self) -> tuple[dt.date, dt.date]:
        today = dt.date.today()
        return (
            today - dt.timedelta(days=self.default_days_back),
            today + dt.timedelta(days=self.default_days_forward),
        )

    def clean(self):
        data = super().clean()
        if "date_from" in self.fields:
            d_from, d_to = data.get("date_from"), data.get("date_to")
            if d_from and d_to and d_from > d_to:
                raise forms.ValidationError(_("«من تاريخ» يجب أن يسبق «إلى تاريخ»."))
        return data

    def resolved_filters(self) -> dict | None:
        """The exact filter dict the builder should use, or ``None`` when a
        bound submission failed validation.

        The report form carries a hidden ``_run`` marker. When it is present the
        user actually submitted the filter form, so the cleaned values are used
        verbatim — an unchecked box or a cleared date really means "off". When
        it is absent (a fresh page load, a pagination link, a bare "export CSV"
        link) the field ``initial``s and the default date window apply, so
        page 2 never disagrees with page 1 (cf. buglog bug-055).
        """
        if self.is_bound and not self.is_valid():
            return None
        if self.is_bound and "_run" in self.data:
            return dict(self.cleaned_data)

        data = {
            name: self.get_initial_for_field(field, name) for name, field in self.fields.items()
        }
        if self.apply_default_window and "date_from" in self.fields:
            data["date_from"], data["date_to"] = self._default_bounds()
        return data


# ── general reports ───────────────────────────────────────────────────────
class CaseReportForm(BaseReportForm):
    date_field_label = _("الفتح")
    apply_default_window = False  # a case report is usually "all open", not a window

    status = forms.ChoiceField(
        label=_("الحالة"), required=False, choices=[("", _("كل الحالات")), *CaseStatus.choices]
    )
    priority = forms.ChoiceField(
        label=_("الأولوية"),
        required=False,
        choices=[("", _("كل الأولويات")), *CasePriority.choices],
    )
    case_type = forms.ModelChoiceField(
        label=_("النوع"),
        required=False,
        queryset=CaseType.objects.order_by("name"),
        empty_label=_("كل الأنواع"),
    )
    lawyer = forms.ModelChoiceField(
        label=_("المحامي المسؤول"),
        required=False,
        queryset=_staff_queryset(),
        empty_label=_("كل المحامين"),
    )
    court = forms.ModelChoiceField(
        label=_("المحكمة"), required=False, queryset=None, empty_label=_("كل المحاكم")
    )
    client = forms.ModelChoiceField(
        label=_("الموكل"), required=False, queryset=None, empty_label=_("كل الموكلين")
    )
    open_only = forms.BooleanField(label=_("المفتوحة فقط"), required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from courts.models import Court

        self.fields["court"].queryset = Court.objects.for_user(self.user).order_by("name")
        self.fields["client"].queryset = scoped_client_queryset(self.user).order_by("full_name")
        self.fields["lawyer"].queryset = _staff_queryset()
        if not self.is_bound:
            self.fields["open_only"].initial = True


class ClientReportForm(BaseReportForm):
    apply_default_window = False  # a client census has no date window

    client_type = forms.ChoiceField(
        label=_("النوع"), required=False, choices=[("", _("الكل")), *ClientType.choices]
    )
    status = forms.ChoiceField(
        label=_("الحالة"), required=False, choices=[("", _("كل الحالات")), *ClientStatus.choices]
    )
    with_active_cases = forms.BooleanField(label=_("لديه قضايا نشطة فقط"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["date_from"]
        del self.fields["date_to"]


class HearingReportForm(BaseReportForm):
    date_field_label = _("الجلسة")
    default_days_back = 30
    default_days_forward = 90  # a hearing report is mostly forward-looking

    status = forms.ChoiceField(
        label=_("الحالة"), required=False, choices=[("", _("كل الحالات")), *HearingStatus.choices]
    )
    court = forms.ModelChoiceField(
        label=_("المحكمة"), required=False, queryset=None, empty_label=_("كل المحاكم")
    )
    lawyer = forms.ModelChoiceField(
        label=_("المحامي"), required=False, queryset=None, empty_label=_("كل المحامين")
    )
    client = forms.ModelChoiceField(
        label=_("الموكل"), required=False, queryset=None, empty_label=_("كل الموكلين")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from courts.models import Court

        self.fields["court"].queryset = Court.objects.for_user(self.user).order_by("name")
        self.fields["lawyer"].queryset = _staff_queryset()
        self.fields["client"].queryset = scoped_client_queryset(self.user).order_by("full_name")


class TaskReportForm(BaseReportForm):
    date_field_label = _("الاستحقاق")
    apply_default_window = False

    status = forms.ChoiceField(
        label=_("الحالة"), required=False, choices=[("", _("كل الحالات")), *TaskStatus.choices]
    )
    assigned_to = forms.ModelChoiceField(
        label=_("الموظف"), required=False, queryset=None, empty_label=_("كل الموظفين")
    )
    overdue_only = forms.BooleanField(label=_("المتأخرة فقط"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = _staff_queryset()


class DeadlineReportForm(BaseReportForm):
    date_field_label = _("الاستحقاق")
    apply_default_window = False

    status = forms.ChoiceField(
        label=_("الحالة"), required=False, choices=[("", _("كل الحالات")), *DeadlineStatus.choices]
    )
    overdue_only = forms.BooleanField(label=_("الفائتة فقط"), required=False)


# ── financial reports (all gated on finance.view) ─────────────────────────
class _FinanceReportForm(BaseReportForm):
    currency = forms.ChoiceField(
        label=_("العملة"), required=False, choices=[("", _("كل العملات")), *Currency.choices]
    )
    client = forms.ModelChoiceField(
        label=_("الموكل"), required=False, queryset=None, empty_label=_("كل الموكلين")
    )
    case = forms.ModelChoiceField(
        label=_("القضية"), required=False, queryset=None, empty_label=_("كل القضايا")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = scoped_client_queryset(self.user).order_by("full_name")
        self.fields["case"].queryset = scoped_case_queryset(self.user)


class RevenueReportForm(_FinanceReportForm):
    date_field_label = _("الإصدار")


class PaymentReportForm(_FinanceReportForm):
    date_field_label = _("الدفع")

    method = forms.ChoiceField(
        label=_("طريقة الدفع"),
        required=False,
        choices=[("", _("كل الطرق")), *PaymentMethod.choices],
    )


class OutstandingReportForm(_FinanceReportForm):
    """Outstanding invoices are "as of today" — no date window."""

    date_field_label = _("الاستحقاق")
    apply_default_window = False

    overdue_only = forms.BooleanField(label=_("المتأخرة فقط"), required=False)


class ExpenseReportForm(_FinanceReportForm):
    date_field_label = _("الصرف")

    category = forms.ChoiceField(
        label=_("التصنيف"),
        required=False,
        choices=[("", _("كل التصنيفات")), *ExpenseCategory.choices],
    )


class CaseFinancialsReportForm(_FinanceReportForm):
    """Per-case roll-up — the window filters invoices/expenses by their own
    date; leaving it empty covers the whole history."""

    date_field_label = _("الحركة")
    apply_default_window = False
