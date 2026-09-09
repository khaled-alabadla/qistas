"""End-to-end HTTP smoke for the Phase 5 surface (tasks + deadlines + dashboard)."""

import datetime as dt

import pytest
from django.urls import reverse

from cases.tests.factories import CaseFactory
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


def test_phase5_pages_render(client, office_manager):
    client.force_login(office_manager)
    case = CaseFactory()
    task = TaskFactory(case=case, assigned_to=office_manager)
    deadline = DeadlineFactory(case=case)
    urls = [
        reverse("core:landing"),
        reverse("tasks:list"),
        reverse("tasks:list") + "?mine=on&overdue=on",
        reverse("tasks:create"),
        reverse("tasks:create") + f"?case={case.pk}",
        reverse("tasks:detail", args=[task.pk]),
        reverse("tasks:update", args=[task.pk]),
        reverse("tasks:deadlines"),
        reverse("tasks:deadline_create"),
        reverse("tasks:deadline_detail", args=[deadline.pk]),
        reverse("tasks:deadline_update", args=[deadline.pk]),
        reverse("cases:detail", args=[case.pk]) + "?tab=tasks",
        reverse("agenda:month"),
    ]
    for url in urls:
        assert client.get(url).status_code == 200, url


def test_landing_widgets_present(client, office_manager):
    TaskFactory(assigned_to=office_manager, due_date=dt.date.today() - dt.timedelta(days=1))
    client.force_login(office_manager)
    ctx = client.get(reverse("core:landing")).context
    assert ctx["has_widgets"] is True
    assert ctx["overdue_count"] == 1
