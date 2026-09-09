from __future__ import annotations

from django.urls import path

from hearings import views

app_name = "hearings"

urlpatterns = [
    path("", views.HearingListView.as_view(), name="list"),
    path("new/", views.HearingScheduleView.as_view(), name="schedule"),
    path("<int:pk>/", views.HearingDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.HearingUpdateView.as_view(), name="update"),
    path("<int:pk>/complete/", views.HearingCompleteView.as_view(), name="complete"),
    path("<int:pk>/postpone/", views.HearingPostponeView.as_view(), name="postpone"),
    path("<int:pk>/cancel/", views.hearing_cancel, name="cancel"),
]
