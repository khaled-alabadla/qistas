"""Finance forms — create/edit, filters, and the action forms (issue / pay /
reverse / credit note). All monetary *results* are computed in the service, not
here; these forms only collect and range-check the raw inputs."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from core.forms import scoped_case_queryset, scoped_client_queryset, with_current_choice
from core.money import Currency
from finance.models import (
    Expense,
    ExpenseCategory,
    FeeAgreement,
    FeeAgreementStatus,
    FeeType,
    Invoice,
    InvoiceLineItem,
    PaymentMethod,
)


class _DateInput(forms.DateInput):
    input_type = "date"


def _scoped_fee_agreements(user):
    return FeeAgreement.objects.for_user(user).select_related("case").order_by("-created_at")


# ── FeeAgreement ───────────────────────────────────────────
class FeeAgreementForm(forms.ModelForm):
    class Meta:
        model = FeeAgreement
        fields = [
            "case",
            "fee_type",
            "fixed_amount",
            "hourly_rate",
            "contingency_percent",
            "currency",
            "agreed_on",
            "start_date",
            "end_date",
            "description",
            "notes",
        ]
        widgets = {
            "agreed_on": _DateInput(),
            "start_date": _DateInput(),
            "end_date": _DateInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance if self.instance and self.instance.pk else None
        self.fields["case"].queryset = with_current_choice(
            scoped_case_queryset(user), getattr(inst, "case_id", None)
        )
        for name in (
            "fixed_amount",
            "hourly_rate",
            "contingency_percent",
            "agreed_on",
            "start_date",
            "end_date",
            "description",
            "notes",
        ):
            self.fields[name].required = False


class FeeAgreementFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("المرجع، الوصف…"), "type": "search"}),
    )
    status = forms.ChoiceField(
        label=_("الحالة"), required=False, choices=[("", _("الكل")), *FeeAgreementStatus.choices]
    )
    fee_type = forms.ChoiceField(
        label=_("النوع"), required=False, choices=[("", _("كل الأنواع")), *FeeType.choices]
    )


class FeeAgreementStatusForm(forms.Form):
    status = forms.ChoiceField(label=_("الحالة الجديدة"), choices=FeeAgreementStatus.choices)


# ── Invoice (draft) ────────────────────────────────────────
class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "client",
            "case",
            "fee_agreement",
            "due_date",
            "currency",
            "discount",
            "tax_rate",
            "notes",
        ]
        widgets = {
            "due_date": _DateInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance if self.instance and self.instance.pk else None
        self.fields["client"].queryset = with_current_choice(
            scoped_client_queryset(user), getattr(inst, "client_id", None)
        )
        self.fields["case"].queryset = with_current_choice(
            scoped_case_queryset(user), getattr(inst, "case_id", None)
        )
        self.fields["fee_agreement"].queryset = with_current_choice(
            _scoped_fee_agreements(user), getattr(inst, "fee_agreement_id", None)
        )
        for name in ("case", "fee_agreement", "due_date", "notes"):
            self.fields[name].required = False
        self.fields["discount"].required = False
        self.fields["tax_rate"].required = False

    def clean_discount(self):
        v = self.cleaned_data.get("discount")
        if v is not None and v < 0:
            raise forms.ValidationError(_("الخصم لا يمكن أن يكون سالبًا."))
        return v

    def clean_tax_rate(self):
        v = self.cleaned_data.get("tax_rate")
        if v is not None and not (0 <= v <= 100):
            raise forms.ValidationError(_("نسبة الضريبة بين 0 و 100."))
        return v


class InvoiceFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("رقم الفاتورة…"), "type": "search"}),
    )
    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("الكل عدا الملغاة")), *Invoice._meta.get_field("status").choices],
    )
    overdue = forms.BooleanField(label=_("المتأخرة فقط"), required=False)


class LineItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceLineItem
        fields = ["description", "quantity", "unit_price"]

    def clean_quantity(self):
        v = self.cleaned_data["quantity"]
        if v <= 0:
            raise forms.ValidationError(_("الكمية يجب أن تكون أكبر من صفر."))
        return v

    def clean_unit_price(self):
        v = self.cleaned_data["unit_price"]
        if v < 0:
            raise forms.ValidationError(_("سعر الوحدة لا يمكن أن يكون سالبًا."))
        return v


class IssueInvoiceForm(forms.Form):
    issue_date = forms.DateField(label=_("تاريخ الإصدار"), required=False, widget=_DateInput())


# ── Payment ────────────────────────────────────────────────
class PaymentForm(forms.Form):
    amount = forms.DecimalField(label=_("المبلغ"), max_digits=14, decimal_places=2, min_value=0)
    paid_on = forms.DateField(label=_("تاريخ الدفع"), widget=_DateInput())
    method = forms.ChoiceField(label=_("طريقة الدفع"), choices=PaymentMethod.choices)
    external_reference = forms.CharField(label=_("مرجع خارجي"), required=False, max_length=100)
    note = forms.CharField(
        label=_("ملاحظات"), required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean_amount(self):
        v = self.cleaned_data["amount"]
        if v <= 0:
            raise forms.ValidationError(_("المبلغ يجب أن يكون أكبر من صفر."))
        return v


class PaymentFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": _("مرجع الدفعة، رقم الفاتورة…"), "type": "search"}
        ),
    )
    method = forms.ChoiceField(
        label=_("الطريقة"), required=False, choices=[("", _("الكل")), *PaymentMethod.choices]
    )


class PaymentReversalForm(forms.Form):
    amount = forms.DecimalField(
        label=_("مبلغ الاسترجاع"), max_digits=14, decimal_places=2, min_value=0
    )
    reversed_on = forms.DateField(label=_("تاريخ الاسترجاع"), widget=_DateInput())
    reason = forms.CharField(label=_("السبب"), widget=forms.Textarea(attrs={"rows": 3}))

    def clean_amount(self):
        v = self.cleaned_data["amount"]
        if v <= 0:
            raise forms.ValidationError(_("المبلغ يجب أن يكون أكبر من صفر."))
        return v


# ── CreditNote ─────────────────────────────────────────────
class CreditNoteForm(forms.Form):
    amount = forms.DecimalField(label=_("المبلغ"), max_digits=14, decimal_places=2, min_value=0)
    issued_on = forms.DateField(label=_("تاريخ الإصدار"), widget=_DateInput())
    reason = forms.CharField(label=_("السبب"), widget=forms.Textarea(attrs={"rows": 3}))

    def clean_amount(self):
        v = self.cleaned_data["amount"]
        if v <= 0:
            raise forms.ValidationError(_("المبلغ يجب أن يكون أكبر من صفر."))
        return v


# ── Expense ────────────────────────────────────────────────
class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "description",
            "amount",
            "currency",
            "category",
            "spent_on",
            "case",
            "client",
            "note",
        ]
        widgets = {
            "spent_on": _DateInput(),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance if self.instance and self.instance.pk else None
        self.fields["case"].queryset = with_current_choice(
            scoped_case_queryset(user), getattr(inst, "case_id", None)
        )
        self.fields["client"].queryset = with_current_choice(
            scoped_client_queryset(user), getattr(inst, "client_id", None)
        )
        for name in ("case", "client", "note"):
            self.fields[name].required = False

    def clean_amount(self):
        v = self.cleaned_data["amount"]
        if v <= 0:
            raise forms.ValidationError(_("المبلغ يجب أن يكون أكبر من صفر."))
        return v


class ExpenseFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("المرجع، الوصف…"), "type": "search"}),
    )
    category = forms.ChoiceField(
        label=_("التصنيف"),
        required=False,
        choices=[("", _("كل التصنيفات")), *ExpenseCategory.choices],
    )


# convenience re-export
CURRENCIES = Currency
