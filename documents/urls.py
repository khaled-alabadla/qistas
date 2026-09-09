from __future__ import annotations

from django.urls import path

from documents import views

app_name = "documents"

urlpatterns = [
    path("", views.DocumentListView.as_view(), name="list"),
    path("new/", views.DocumentUploadView.as_view(), name="upload"),
    path("<int:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.DocumentUpdateView.as_view(), name="update"),
    path("<int:pk>/download/", views.document_download, name="download"),
    path("<int:pk>/retire/", views.document_retire, name="retire"),
]
