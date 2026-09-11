"""Client forms — create/edit + list filter."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from clients.models import Client, ClientStatus, ClientType
from core.permissions.capabilities import Capability, can

SENSITIVE_FORM_FIELDS = ("national_id", "registration_number")


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "type",
            "full_name",
            "company_name",
            "national_id",
            "registration_number",
            "phone",
            "secondary_phone",
            "email",
            "address",
            "city",
            "status",
            "notes",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "phone": forms.TextInput(attrs={"dir": "ltr", "inputmode": "tel"}),
            "secondary_phone": forms.TextInput(attrs={"dir": "ltr", "inputmode": "tel"}),
            "national_id": forms.TextInput(attrs={"dir": "ltr", "autocomplete": "off"}),
            "email": forms.EmailInput(attrs={"dir": "ltr"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # `status` is create-only here. On edit it must go through
        # `archive_client` / `restore_client` (the dedicated, audited
        # transitions) — never a silent field on the general edit form, or a
        # save could archive/restore a client as `client.updated` with no
        # `CLIENT_ARCHIVED`/`CLIENT_RESTORED` audit event and no transition
        # guard (matches the `CaseForm`/`ContractForm` house pattern — status
        # is never on the edit ModelForm; docs/adr/0036 hardening review).
        if self.instance and self.instance.pk:
            self.fields.pop("status", None)
        # Hide the highly-sensitive fields from users without the capability so
        # they can neither read nor blank them (docs/adr/0009).
        if user is not None and not can(user, Capability.CLIENTS_VIEW_SENSITIVE):
            for name in SENSITIVE_FORM_FIELDS:
                self.fields.pop(name, None)
        for name in (
            "full_name",
            "company_name",
            "email",
            "secondary_phone",
            "address",
            "city",
            "notes",
            "registration_number",
        ):
            if name in self.fields:
                self.fields[name].required = False

    # The individual↔company name rule is enforced once, by ``Client.clean()``
    # (run via ModelForm._post_clean) and the DB CheckConstraint — no duplicate
    # here.


class ClientFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("اسم، رقم عميل، هاتف…"), "type": "search"}),
    )
    type = forms.ChoiceField(
        label=_("النوع"),
        required=False,
        choices=[("", _("كل الأنواع")), *ClientType.choices],
    )
    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("كل الحالات (عدا المؤرشفة)")), *ClientStatus.choices],
    )
