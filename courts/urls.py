from __future__ import annotations

from django.urls import path

from courts import views

app_name = "courts"

urlpatterns = [
    path("", views.CourtListView.as_view(), name="list"),
    path("new/", views.CourtCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CourtDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.CourtUpdateView.as_view(), name="update"),
    path("<int:pk>/active/", views.court_set_active, name="set_active"),
]
