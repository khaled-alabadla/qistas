from __future__ import annotations

from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password_change"),
    path(
        "password/change/done/",
        views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("password/reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "password/reset/sent/",
        views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/done/",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    # ── MFA (docs/adr/0017) ──
    path("mfa/setup/", views.mfa_setup, name="mfa_setup"),
    path("mfa/activate/", views.mfa_activate, name="mfa_activate"),
    path("mfa/manage/", views.mfa_manage, name="mfa_manage"),
    path("mfa/codes/regenerate/", views.mfa_regenerate_codes, name="mfa_regenerate_codes"),
    path("mfa/disable/", views.mfa_disable, name="mfa_disable"),
    path("mfa/verify/", views.mfa_token, name="mfa_token"),
]
