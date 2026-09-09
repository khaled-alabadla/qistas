import datetime as dt

import pytest

from tasks.models import Deadline, DeadlineStatus, Task, TaskStatus
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db

TODAY = dt.date.today()


def test_for_user_denies_anon_allows_authed(user):
    TaskFactory.create_batch(2)
    assert Task.objects.for_user(None).count() == 0
    assert Task.objects.for_user(user).count() == 2


def test_task_is_overdue_computed():
    past = TaskFactory(due_date=TODAY - dt.timedelta(days=1), status=TaskStatus.NEW)
    future = TaskFactory(due_date=TODAY + dt.timedelta(days=1))
    done_past = TaskFactory(due_date=TODAY - dt.timedelta(days=5), status=TaskStatus.DONE)
    no_date = TaskFactory(due_date=None)
    assert past.is_overdue is True
    assert future.is_overdue is False
    assert done_past.is_overdue is False
    assert no_date.is_overdue is False
    assert set(Task.objects.overdue()) == {past}


def test_task_no_overdue_status_value():
    assert "overdue" not in TaskStatus.values  # docs/adr/0006


def test_alive_excludes_soft_deleted():
    t = TaskFactory()
    TaskFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    assert list(Task.objects.alive()) == [t]


def test_deadline_overdue_and_no_delete_permission():
    od = DeadlineFactory(due_date=TODAY - dt.timedelta(days=1), status=DeadlineStatus.PENDING)
    met = DeadlineFactory(due_date=TODAY - dt.timedelta(days=1), status=DeadlineStatus.MET)
    assert od.is_overdue is True
    assert met.is_overdue is False
    assert set(Deadline.objects.overdue()) == {od}
    assert "delete" not in Deadline._meta.default_permissions
