from __future__ import annotations

from django.urls import path

from cases import views

app_name = "cases"

urlpatterns = [
    path("", views.CaseListView.as_view(), name="list"),
    path("new/", views.CaseCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CaseDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.CaseUpdateView.as_view(), name="update"),
    path("<int:pk>/status/", views.case_status, name="status"),
    path("<int:pk>/confidential/", views.CaseConfidentialUpdateView.as_view(), name="confidential"),
    path("<int:pk>/parties/new/", views.CasePartyAddView.as_view(), name="party_add"),
    path("<int:pk>/parties/<int:party_pk>/remove/", views.case_party_remove, name="party_remove"),
    path("<int:pk>/notes/new/", views.CaseNoteAddView.as_view(), name="note_add"),
    path("<int:pk>/lawyers/add/", views.case_lawyer_add, name="lawyer_add"),
    path("<int:pk>/lawyers/<int:user_pk>/remove/", views.case_lawyer_remove, name="lawyer_remove"),
]
