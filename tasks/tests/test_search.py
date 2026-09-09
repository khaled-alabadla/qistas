import datetime as dt

import pytest

from tasks.selectors import deadline_list, task_list
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


def test_task_selector_search_and_filters(office_manager):
    a = TaskFactory(title="تحضير مرافعة الاستئناف", priority="high")
    TaskFactory(title="مهمة عادية", priority="low")
    assert a in list(task_list(user=office_manager, query="الاستئناف"))
    assert list(task_list(user=office_manager, priority="high")) == [a]


def test_deadline_selector_search(office_manager):
    a = DeadlineFactory(title="مهلة الطعن بالنقض")
    DeadlineFactory(title="مهلة أخرى")
    assert list(deadline_list(user=office_manager, query="النقض")) == [a]


def test_calendar_items_includes_tasks_and_deadlines(user):
    today = dt.date.today()
    TaskFactory(due_date=today + dt.timedelta(days=2))
    DeadlineFactory(due_date=today + dt.timedelta(days=3))
    from django.utils import timezone

    from tasks.selectors import calendar_items

    start = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
    end = start + dt.timedelta(days=10)
    items = calendar_items(user, start, end)
    kinds = {i["kind"] for i in items}
    assert kinds == {"task", "deadline"}
    assert all(i["all_day"] for i in items)


def test_search_field_set_and_trgm_in_sync():
    from importlib import import_module

    from tasks.models import DEADLINE_SEARCH_FIELDS, TASK_SEARCH_FIELDS

    mod = import_module("tasks.migrations.0002_task_search_indexes")
    assert tuple(sorted(mod.TASK_TRGM_COLUMNS)) == tuple(sorted(TASK_SEARCH_FIELDS))
    assert tuple(sorted(mod.DEADLINE_TRGM_COLUMNS)) == tuple(sorted(DEADLINE_SEARCH_FIELDS))
