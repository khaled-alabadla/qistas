"""Authentication + MFA views (docs/adr/0004, 0017, 0027)."""

from __future__ import annotations

from axes.handlers.proxy import AxesProxyHandler
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts import otp as mfa
from accounts.forms import ConfirmForm, LoginForm, TOTPTokenForm
from accounts.otp import MFA_NEXT_SESSION_KEY


# ── django-axes lockout page ────────────────────────────────
def axes_lockout_response(request, credentials=None, *args, **kwargs):
    username = ""
    if credentials:
        username = credentials.get("username", "")
    elif request.method == "POST":
        username = request.POST.get("username", "")
    try:
        from audit.events import log_event
        from audit.models import AuditAction

        log_event(
            request,
            AuditAction.LOCKOUT,
            entity_type="accounts.user",
            object_repr=str(username)[:200],
        )
    except Exception:  # pragma: no cover - audit must never block the response
        pass
    return render(request, "registration/lockout.html", status=429)


# ── Login / logout ─────────────────────────────────────────
class LoginView(auth_views.LoginView):
    form_class = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        # A locked account gets the lockout page for ANY password (the backend
        # otherwise degrades to a generic "invalid" message on the right one).
        if request.method == "POST":
            username = request.POST.get("username", "").strip()
            if username and AxesProxyHandler.is_locked(request, {"username": username}):
                return axes_lockout_response(request, {"username": username})
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.get_user()
        # Password step done. If the account has a confirmed authenticator, the
        # OTP step has not happened yet this session -> route to it.
        if mfa.confirmed_totp(user):
            self.request.session[MFA_NEXT_SESSION_KEY] = self.get_success_url()
            return redirect("accounts:mfa_token")
        return response


class LogoutView(auth_views.LogoutView):
    template_name = "registration/logged_out.html"


# ── Password change (also the must-change-password destination) ──
class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)
        if getattr(self.request.user, "must_change_password", False):
            self.request.user.must_change_password = False
            self.request.user.save(update_fields=["must_change_password"])
        return response


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "registration/password_change_done.html"


# ── Password reset chain ───────────────────────────────────
class PasswordResetView(auth_views.PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"


# ── MFA enrollment ─────────────────────────────────────────
@login_required
@require_http_methods(["GET"])
def mfa_setup(request):
    if mfa.confirmed_totp(request.user):
        return redirect("accounts:mfa_manage")
    device = mfa.get_or_create_unconfirmed_totp(request.user)
    return render(
        request,
        "accounts/mfa_setup.html",
        {
            "secret": device.key,
            "qr_svg": mfa.qr_svg(device.config_url),
            "form": TOTPTokenForm(),
        },
    )


@login_required
@require_http_methods(["POST"])
def mfa_activate(request):
    device = mfa.get_or_create_unconfirmed_totp(request.user)
    form = TOTPTokenForm(request.POST)
    if form.is_valid() and device.verify_token(form.cleaned_data["token"]):
        device.confirmed = True
        device.save(update_fields=["confirmed"])
        otp_login(request, device)
        codes = mfa.generate_recovery_codes(request.user)
        messages.success(request, _("تم تفعيل التحقق بخطوتين."))
        return render(request, "accounts/mfa_recovery_codes.html", {"codes": codes})
    messages.error(request, _("الرمز غير صحيح. حاول مرة أخرى."))
    return render(
        request,
        "accounts/mfa_setup.html",
        {
            "secret": device.key,
            "qr_svg": mfa.qr_svg(device.config_url),
            "form": form,
        },
    )


@login_required
def mfa_manage(request):
    device = mfa.confirmed_totp(request.user)
    has_recovery = StaticDevice.objects.filter(
        user=request.user, name=mfa.RECOVERY_DEVICE_NAME
    ).exists()
    return render(
        request,
        "accounts/mfa_manage.html",
        {"device": device, "has_recovery": has_recovery},
    )


@login_required
@require_http_methods(["POST"])
def mfa_regenerate_codes(request):
    if not mfa.confirmed_totp(request.user):
        return redirect("accounts:mfa_setup")
    codes = mfa.generate_recovery_codes(request.user)
    messages.success(request, _("تم إنشاء رموز استرداد جديدة. الرموز القديمة لم تعد صالحة."))
    return render(request, "accounts/mfa_recovery_codes.html", {"codes": codes})


@login_required
def mfa_disable(request):
    if request.method == "POST":
        form = ConfirmForm(request.POST)
        if form.is_valid():
            TOTPDevice.objects.filter(user=request.user).delete()
            StaticDevice.objects.filter(user=request.user).delete()
            messages.warning(request, _("تم إيقاف التحقق بخطوتين."))
            return redirect("accounts:mfa_manage")
    else:
        form = ConfirmForm()
    return render(request, "accounts/mfa_disable.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def mfa_token(request):
    """Post-login second step: verify TOTP or a recovery code."""
    if request.user.is_verified():
        return redirect(request.session.pop(MFA_NEXT_SESSION_KEY, "core:landing"))

    form = TOTPTokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        token = form.cleaned_data["token"]
        for device in (
            *TOTPDevice.objects.filter(user=request.user, confirmed=True),
            *StaticDevice.objects.filter(user=request.user),
        ):
            if device.verify_token(token):
                otp_login(request, device)
                dest = request.session.pop(MFA_NEXT_SESSION_KEY, None)
                return redirect(dest or "core:landing")
        messages.error(request, _("رمز غير صحيح."))
    return render(request, "accounts/mfa_token.html", {"form": form})
