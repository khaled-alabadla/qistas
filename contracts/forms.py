"""Contract forms — create/edit, list filter, status action (spec §37)."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from contracts.models import Contract, ContractStatus, ContractType
from core.forms import scoped_case_queryset, scoped_client_queryset, with_current_choice

# The create form offers only these; `expired` / `cancelled` are reached through
# the guarded status action (docs/adr/0031).
CREATE_STATUS_CHOICES = [
    (ContractStatus.DRAFT.value, ContractStatus.DRAFT.label),
    (ContractStatus.ACTIVE.value, ContractStatus.ACTIVE.label),
]


class _DateInput(forms.DateInput):
    input_type = "date"


class ContractForm(forms.ModelForm):
    status = forms.ChoiceField(
        label=_("الحالة"), choices=CREATE_STATUS_CHOICES, initial=ContractStatus.DRAFT
    )

    class Meta:
        model = Contract
        fields = [
            "title",
            "contract_type",
            "client",
            "case",
            "start_date",
            "end_date",
            "value",
            "currency",
            "description",
            "notes",
        ]
        widgets = {
            "start_date": _DateInput(),
            "end_date": _DateInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
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
        self.fields["case"].required = False
        self.fields["case"].empty_label = _("— لا شيء —")
        for name in ("end_date", "value", "description", "notes"):
            self.fields[name].required = False

        # `status` is edit-only-immutable: it moves through the status action.
        if inst is not None:
            del self.fields["status"]

    # end_date >= start_date is enforced by Contract.clean() via the ModelForm's
    # _post_clean → full_clean, and by a DB CheckConstraint (docs/adr/0031).


class ContractFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("رقم العقد، العنوان…"), "type": "search"}),
    )
    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("المفتوحة")), *ContractStatus.choices],
    )
    contract_type = forms.ChoiceField(
        label=_("النوع"),
        required=False,
        choices=[("", _("كل الأنواع")), *ContractType.choices],
    )
    expiring = forms.BooleanField(label=_("قريبة من الانتهاء"), required=False)


class ContractStatusForm(forms.Form):
    status = forms.ChoiceField(label=_("الحالة الجديدة"), choices=ContractStatus.choices)
