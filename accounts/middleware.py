"""
Session / auth middleware (docs/architecture.md §5).

Order in ``config.settings.base.MIDDLEWARE``:
    LoginRequired → MustChangePassword → IdleTimeout → MFAEnforcement
All run after AuthenticationMiddleware + OTPMiddleware.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from accounts.otp import MFA_NEXT_SESSION_KEY


def _static_or_media(path: str) -> bool:
    for url in (settings.STATIC_URL, settings.MEDIA_URL):
        if url and path.startswith("/" + url.lstrip("/")):
            return True
    return False


# View names reachable without authentication.
PUBLIC_VIEW_NAMES = {
    "accounts:login",
    "accounts:logout",
    "accounts:password_reset",
    "accounts:password_reset_done",
    "accounts:password_reset_confirm",
    "accounts:password_reset_complete",
    "core:healthz",
}

# Path prefixes always allowed (static/media/admin-own-auth).
PUBLIC_PATH_PREFIXES = ("/admin/",)


def _is_public(request) -> bool:
    path = request.path_info
    if _static_or_media(path):
        return True
    if any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES):
        return True
    match = request.resolver_match
    if match and match.view_name in PUBLIC_VIEW_NAMES:
        return True
    return False


class LoginRequiredMiddleware:
    """Every resolved view requires authentication unless explicitly public.

    Implemented via ``process_view`` so an unresolved URL still returns a themed
    404 rather than redirecting anonymous users to the login page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(view_func, "login_not_required", False):
            return None
        if request.user.is_authenticated:
            return None
        if _is_public(request):
            return None
        return redirect_to_login(request.get_full_path(), reverse("accounts:login"))


class MustChangePasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and getattr(user, "must_change_password", False):
            allowed = {
                reverse("accounts:password_change"),
                reverse("accounts:password_change_done"),
                reverse("accounts:logout"),
            }
            if request.path not in allowed and not _static_or_media(request.path):
                messages.warning(request, _("يجب تعيين كلمة مرور جديدة قبل المتابعة."))
                return redirect("accounts:password_change")
        return self.get_response(request)


class IdleTimeoutMiddleware:
    SESSION_KEY = "_last_activity"

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = int(getattr(settings, "IDLE_TIMEOUT_SECONDS", 1800))

    def __call__(self, request):
        if request.user.is_authenticated and self.timeout > 0:
            now = time.time()
            last = request.session.get(self.SESSION_KEY)
            if last is not None and (now - last) > self.timeout:
                logout(request)
                messages.info(request, _("انتهت الجلسة بسبب عدم النشاط. يُرجى تسجيل الدخول مجددًا."))
                return redirect("accounts:login")
            request.session[self.SESSION_KEY] = now
        return self.get_response(request)


class MFAEnforcementMiddleware:
    """Two independent rules (docs/adr/0017):

    1. **Completion is mandatory once enrolled.** A user with a confirmed
       authenticator who has not passed the OTP step this session is sent to
       ``mfa_token`` — always, regardless of global settings. Opting in means
       the second factor is required.
    2. **Enrollment** is only forced when ``settings.REQUIRE_MFA`` is true or the
       user is in ``settings.MFA_ENFORCED_GROUPS`` (both empty/false by default).
    """

    ALLOWED_VIEW_NAMES = {
        "accounts:mfa_setup",
        "accounts:mfa_activate",
        "accounts:mfa_manage",
        "accounts:mfa_disable",
        "accounts:mfa_token",
        "accounts:logout",
        "core:healthz",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def _enrollment_forced_for(self, user) -> bool:
        if getattr(settings, "REQUIRE_MFA", False):
            return True
        enforced = set(getattr(settings, "MFA_ENFORCED_GROUPS", []))
        if not enforced:
            return False
        return bool(enforced & set(user.groups.values_list("name", flat=True)))

    def _exempt(self, request) -> bool:
        if _static_or_media(request.path):
            return True
        match = request.resolver_match
        return bool(match and match.view_name in self.ALLOWED_VIEW_NAMES)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not user.is_authenticated or self._exempt(request):
            return None

        verified = getattr(user, "is_verified", None)
        already_verified = callable(verified) and verified()
        if already_verified:
            return None

        from accounts.otp import confirmed_totp

        if confirmed_totp(user):
            # Rule 1: enrolled but OTP step not done -> must complete it.
            request.session[MFA_NEXT_SESSION_KEY] = request.get_full_path()
            return redirect("accounts:mfa_token")

        if self._enrollment_forced_for(user):
            # Rule 2: enrollment is forced for this user.
            messages.warning(request, _("يتطلب حسابك تفعيل التحقق بخطوتين للمتابعة."))
            return redirect("accounts:mfa_setup")
        return None

    def __call__(self, request):
        return self.get_response(request)
