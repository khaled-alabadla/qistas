"""Case forms — create/edit, filter, parties, notes, status, assignment, confidential."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from cases.models import (
    Case,
    CaseConfidential,
    CaseParty,
    CasePriority,
    CaseStatus,
    CaseType,
    NoteKind,
)
from clients.models import Client, ClientStatus
from courts.models import Court

User = get_user_model()

LAWYER_GROUPS = ("office_manager", "lawyer", "admin_clerk")


def _lawyer_queryset():
    return User.objects.filter(is_active=True, groups__name__in=LAWYER_GROUPS).distinct()


def _with_current(queryset, instance, attr):
    """Widen ``queryset`` to also include the pk ``instance`` currently references
    on ``attr`` (so an edit form never hides the case's own existing value)."""
    if instance is None:
        return queryset
    current = getattr(instance, attr, None)
    if current is None:
        return queryset
    return (queryset.model.objects.filter(pk=current) | queryset).distinct()


class CaseForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = [
            "title",
            "type",
            "client",
            "assigned_lawyer",
            "court",
            "court_case_number",
            "internal_reference",
            "department",
            "stage",
            "priority",
            "filing_date",
            "claim_amount",
            "description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "filing_date": forms.DateInput(attrs={"type": "date"}),
            "court_case_number": forms.TextInput(attrs={"dir": "ltr"}),
            "claim_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0", "dir": "ltr"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restrict pickers to selectable rows, but always keep the value this case
        # already holds so editing an unrelated field never silently drops a FK
        # (e.g. its CaseType was deactivated, its lawyer left, its client archived).
        inst = self.instance if self.instance and self.instance.pk else None
        self.fields["type"].queryset = _with_current(
            CaseType.objects.filter(is_active=True), inst, "type_id"
        )
        self.fields["client"].queryset = _with_current(
            Client.objects.exclude(status=ClientStatus.ARCHIVED), inst, "client_id"
        )
        self.fields["court"].queryset = _with_current(
            Court.objects.filter(is_active=True), inst, "court_id"
        )
        self.fields["court"].required = False
        self.fields["assigned_lawyer"].queryset = _with_current(
            _lawyer_queryset(), inst, "assigned_lawyer_id"
        )
        self.fields["assigned_lawyer"].required = False
        for name in (
            "court_case_number",
            "internal_reference",
            "department",
            "stage",
            "filing_date",
            "claim_amount",
            "description",
        ):
            self.fields[name].required = False


class CaseConfidentialForm(forms.ModelForm):
    class Meta:
        model = CaseConfidential
        fields = ["legal_notes", "internal_notes"]
        widgets = {
            "legal_notes": forms.Textarea(attrs={"rows": 5}),
            "internal_notes": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False


class CaseFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("رقم القضية، العنوان…"), "type": "search"}),
    )
    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("المفتوحة")), *CaseStatus.choices],
    )
    priority = forms.ChoiceField(
        label=_("الأولوية"),
        required=False,
        choices=[("", _("كل الأولويات")), *CasePriority.choices],
    )
    type = forms.ModelChoiceField(
        label=_("النوع"),
        required=False,
        queryset=CaseType.objects.filter(is_active=True),
        empty_label=_("كل الأنواع"),
    )
    lawyer = forms.ModelChoiceField(
        label=_("المحامي"),
        required=False,
        queryset=_lawyer_queryset(),
        empty_label=_("كل المحامين"),
    )


class CasePartyForm(forms.ModelForm):
    class Meta:
        model = CaseParty
        fields = ["party_role", "name", "phone", "email", "notes", "linked_client"]
        widgets = {
            "phone": forms.TextInput(attrs={"dir": "ltr"}),
            "email": forms.EmailInput(attrs={"dir": "ltr"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["linked_client"].queryset = Client.objects.exclude(status=ClientStatus.ARCHIVED)
        for name in ("phone", "email", "notes", "linked_client"):
            self.fields[name].required = False


class CaseNoteForm(forms.Form):
    kind = forms.ChoiceField(label=_("النوع"), choices=NoteKind.choices, initial=NoteKind.GENERAL)
    body = forms.CharField(label=_("النص"), widget=forms.Textarea(attrs={"rows": 3}))


class CaseStatusForm(forms.Form):
    status = forms.ChoiceField(label=_("الحالة الجديدة"), choices=CaseStatus.choices)


class SupportingLawyerForm(forms.Form):
    lawyer = forms.ModelChoiceField(
        label=_("محامٍ مساند"), queryset=_lawyer_queryset(), empty_label=None
    )
