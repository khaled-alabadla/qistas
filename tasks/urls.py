from __future__ import annotations

from django.urls import path

from tasks import views

app_name = "tasks"

urlpatterns = [
    path("", views.TaskListView.as_view(), name="list"),
    path("new/", views.TaskCreateView.as_view(), name="create"),
    path("<int:pk>/", views.TaskDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.TaskUpdateView.as_view(), name="update"),
    path("<int:pk>/status/", views.task_status, name="status"),
    path("<int:pk>/delete/", views.task_delete, name="delete"),
    path("deadlines/", views.DeadlineListView.as_view(), name="deadlines"),
    path("deadlines/new/", views.DeadlineCreateView.as_view(), name="deadline_create"),
    path("deadlines/<int:pk>/", views.DeadlineDetailView.as_view(), name="deadline_detail"),
    path("deadlines/<int:pk>/edit/", views.DeadlineUpdateView.as_view(), name="deadline_update"),
    path("deadlines/<int:pk>/status/", views.deadline_status, name="deadline_status"),
]
