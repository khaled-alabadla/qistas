from __future__ import annotations

from django.urls import path

from clients import views

app_name = "clients"

urlpatterns = [
    path("", views.ClientListView.as_view(), name="list"),
    path("new/", views.ClientCreateView.as_view(), name="create"),
    path("<int:pk>/", views.ClientDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.ClientUpdateView.as_view(), name="update"),
    path("<int:pk>/archive/", views.ClientArchiveConfirmView.as_view(), name="archive_confirm"),
    path("<int:pk>/archive/do/", views.client_archive, name="archive"),
    path("<int:pk>/restore/", views.client_restore, name="restore"),
]
