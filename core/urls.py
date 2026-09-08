from __future__ import annotations

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("healthz/", views.healthz, name="healthz"),
    path("styleguide/", views.StyleguideView.as_view(), name="styleguide"),
]
