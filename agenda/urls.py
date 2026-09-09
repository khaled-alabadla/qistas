from __future__ import annotations

from django.urls import path

from agenda import views

app_name = "agenda"

urlpatterns = [
    path("", views.AgendaMonthView.as_view(), name="month"),
    path("week/", views.AgendaWeekView.as_view(), name="week"),
    path("day/", views.AgendaDayView.as_view(), name="day"),
]
