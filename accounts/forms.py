"""Auth + MFA forms, themed and Arabic (docs/adr/0003)."""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": _("البريد الإلكتروني أو كلمة المرور غير صحيحة."),
        "inactive": _("هذا الحساب غير مُفعّل."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("البريد الإلكتروني")
        self.fields["username"].widget = forms.EmailInput(
            attrs={"autofocus": True, "autocomplete": "username", "dir": "ltr"}
        )
        self.fields["password"].label = _("كلمة المرور")
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})


class TOTPTokenForm(forms.Form):
    token = forms.CharField(
        label=_("الرمز"),
        max_length=8,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "dir": "ltr",
            }
        ),
        help_text=_("أدخل الرمز من تطبيق المصادقة، أو أحد رموز الاسترداد."),
    )


class ConfirmForm(forms.Form):
    """Simple POST-confirm guard (e.g. disabling MFA)."""

    confirm = forms.BooleanField(label=_("أؤكد هذا الإجراء"), required=True)
