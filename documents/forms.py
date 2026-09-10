"""Document forms — upload, metadata edit, list filter (spec §34–35)."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from cases.models import Case
from clients.models import Client
from contracts.models import Contract
from core.forms import scoped_case_queryset, scoped_client_queryset, with_current_choice
from documents.models import Document, DocumentCategory
from documents.validators import allowed_extensions, validate_upload


def _scoped_contracts(user):
    return Contract.objects.for_user(user).select_related("client").order_by("-created_at")


class _DocLinksMixin:
    """Wire the case/client/contract pickers, scoped to the current user."""

    def _wire_links(self, user, instance=None):
        case_qs = scoped_case_queryset(user)
        client_qs = scoped_client_queryset(user)
        contract_qs = _scoped_contracts(user)
        if instance is not None:
            case_qs = with_current_choice(case_qs, getattr(instance, "case_id", None))
            client_qs = with_current_choice(client_qs, getattr(instance, "client_id", None))
            contract_qs = with_current_choice(contract_qs, getattr(instance, "contract_id", None))
        self.fields["case"].queryset = case_qs
        self.fields["client"].queryset = client_qs
        self.fields["contract"].queryset = contract_qs
        self.fields["case"].required = False
        self.fields["client"].required = False
        self.fields["contract"].required = False


class DocumentUploadForm(_DocLinksMixin, forms.Form):
    file = forms.FileField(
        label=_("الملف"),
        widget=forms.ClearableFileInput(attrs={"accept": ",".join(sorted(allowed_extensions()))}),
    )
    name = forms.CharField(label=_("الاسم"), max_length=250)
    document_type = forms.ChoiceField(
        label=_("النوع"), choices=DocumentCategory.choices, initial=DocumentCategory.OTHER
    )
    description = forms.CharField(
        label=_("الوصف"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    case = forms.ModelChoiceField(
        label=_("القضية"), queryset=Case.objects.none(), required=False, empty_label=_("— لا شيء —")
    )
    client = forms.ModelChoiceField(
        label=_("الموكل"),
        queryset=Client.objects.none(),
        required=False,
        empty_label=_("— لا شيء —"),
    )
    contract = forms.ModelChoiceField(
        label=_("العقد"),
        queryset=Contract.objects.none(),
        required=False,
        empty_label=_("— لا شيء —"),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._wire_links(user)
        self.validated = None

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        self.validated = validate_upload(uploaded)  # raises ValidationError
        return uploaded


class DocumentEditForm(_DocLinksMixin, forms.ModelForm):
    """Metadata only — the file is immutable in Phase 6 (spec §36)."""

    class Meta:
        model = Document
        fields = ["name", "document_type", "description", "case", "client", "contract"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance if self.instance and self.instance.pk else None
        self._wire_links(user, instance=inst)
        self.fields["description"].required = False

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class DocumentFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("اسم المستند، الوصف…"), "type": "search"}),
    )
    document_type = forms.ChoiceField(
        label=_("النوع"),
        required=False,
        choices=[("", _("كل الأنواع")), *DocumentCategory.choices],
    )
