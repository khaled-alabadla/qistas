from __future__ import annotations

from django.urls import path

from reports import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportsIndexView.as_view(), name="index"),
    path("<slug:slug>/", views.ReportView.as_view(), name="detail"),
]
