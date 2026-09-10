from __future__ import annotations

import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from cases.tests.factories import CaseFactory
from hearings.tests.factories import HearingFactory
from notifications.models import Notification
from tasks.tests.factories import TaskFactory

pytestmark = pytest.mark.django_db


def test_command_creates_then_is_safe_to_rerun(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    HearingFactory(case=case, scheduled_at=timezone.now() + dt.timedelta(days=1))
    TaskFactory(assigned_to=lawyer, due_date=dt.date.today() - dt.timedelta(days=1))

    out = StringIO()
    call_command("generate_notifications", stdout=out)
    assert "created 2 notification(s)" in out.getvalue()
    assert Notification.objects.count() == 2

    out2 = StringIO()
    call_command("generate_notifications", stdout=out2)
    assert "created 0 notification(s)" in out2.getvalue()
    assert Notification.objects.count() == 2


def test_command_only_flag(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    HearingFactory(case=case, scheduled_at=timezone.now() + dt.timedelta(days=1))
    TaskFactory(assigned_to=lawyer, due_date=dt.date.today() - dt.timedelta(days=1))

    call_command("generate_notifications", "--only", "task_overdue")
    assert Notification.objects.filter(category="task_overdue").count() == 1
    assert Notification.objects.filter(category="hearing_upcoming").count() == 0


def test_command_no_data_is_a_noop(role_user):
    role_user("office_manager")
    call_command("generate_notifications")
    assert Notification.objects.count() == 0
