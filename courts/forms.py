"""Court forms — create/edit + list filter."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from courts.models import Court, CourtType


class CourtForm(forms.ModelForm):
    class Meta:
        model = Court
        fields = ["name", "type", "city", "department", "address", "phone", "notes", "is_active"]
        widgets = {
            "phone": forms.TextInput(attrs={"dir": "ltr"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "address": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("city", "department", "address", "phone", "notes"):
            self.fields[name].required = False


class CourtFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("اسم المحكمة، المدينة…"), "type": "search"}),
    )
    type = forms.ChoiceField(
        label=_("النوع"),
        required=False,
        choices=[("", _("كل الأنواع")), *CourtType.choices],
    )
    include_inactive = forms.BooleanField(label=_("تضمين غير النشطة"), required=False)
