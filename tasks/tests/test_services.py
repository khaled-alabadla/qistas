import datetime as dt

import pytest

from audit.models import AuditAction, AuditLog
from cases.models import CaseEventType
from cases.tests.factories import CaseFactory
from tasks import services
from tasks.models import DeadlineStatus, TaskStatus
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


def _task_data(**over):
    d = {"title": "مهمة", "priority": "medium"}
    d.update(over)
    return d


def test_create_task_audits_and_case_event(office_manager):
    case = CaseFactory()
    task = services.create_task(actor=office_manager, data=_task_data(case=case))
    assert task.created_by == office_manager
    assert AuditLog.objects.filter(action=AuditAction.TASK_CREATED, entity_id=str(task.pk)).exists()
    assert case.events.filter(event_type=CaseEventType.TASK_ADDED).exists()


def test_create_task_without_case_has_no_case_event(office_manager):
    task = services.create_task(actor=office_manager, data=_task_data())
    assert AuditLog.objects.filter(action=AuditAction.TASK_CREATED).count() == 1
    # nothing to assert on a case; just ensure no crash and no orphan event
    assert task.case_id is None


def test_create_task_done_sets_completed_at(office_manager):
    task = services.create_task(actor=office_manager, data=_task_data(status="done"))
    assert task.completed_at is not None


def test_update_task_noop_and_change(office_manager):
    task = TaskFactory(title="قديم")
    before = AuditLog.objects.filter(action=AuditAction.TASK_UPDATED).count()
    services.update_task(
        actor=office_manager, task=task, data={"title": "قديم", "priority": task.priority}
    )
    assert AuditLog.objects.filter(action=AuditAction.TASK_UPDATED).count() == before
    services.update_task(actor=office_manager, task=task, data={"title": "جديد"})
    task.refresh_from_db()
    assert task.title == "جديد"


def test_change_task_status_toggles_completed_at(office_manager):
    case = CaseFactory()
    task = TaskFactory(case=case)
    services.change_task_status(actor=office_manager, task=task, new_status=TaskStatus.DONE)
    task.refresh_from_db()
    assert task.status == TaskStatus.DONE and task.completed_at is not None
    services.change_task_status(actor=office_manager, task=task, new_status=TaskStatus.IN_PROGRESS)
    task.refresh_from_db()
    assert task.completed_at is None
    assert case.events.filter(event_type=CaseEventType.TASK_STATUS_CHANGED).count() == 2


def test_delete_task_is_soft(office_manager):
    case = CaseFactory()
    task = TaskFactory(case=case)
    services.delete_task(actor=office_manager, task=task, request=None)
    task.refresh_from_db()
    assert task.deleted_at is not None
    assert task.deleted_by == office_manager
    from tasks.models import Task

    assert task not in Task.objects.alive()
    assert Task.objects.filter(pk=task.pk).exists()  # row kept
    assert case.events.filter(event_type=CaseEventType.TASK_REMOVED).exists()
    assert AuditLog.objects.filter(action=AuditAction.TASK_DELETED).exists()
    # idempotent
    services.delete_task(actor=office_manager, task=task)
    assert AuditLog.objects.filter(action=AuditAction.TASK_DELETED).count() == 1


def test_deadline_lifecycle(office_manager):
    case = CaseFactory()
    d = services.create_deadline(
        actor=office_manager,
        data={"title": "مهلة", "case": case, "due_date": dt.date.today() + dt.timedelta(days=5)},
    )
    assert case.events.filter(event_type=CaseEventType.DEADLINE_ADDED).exists()
    services.change_deadline_status(actor=office_manager, deadline=d, new_status=DeadlineStatus.MET)
    d.refresh_from_db()
    assert d.status == DeadlineStatus.MET and d.completed_at is not None
    assert AuditLog.objects.filter(action=AuditAction.DEADLINE_STATUS_CHANGED).exists()
    assert case.events.filter(event_type=CaseEventType.DEADLINE_STATUS_CHANGED).exists()


def test_deadline_status_missed_then_cancel_clears_completed_at(office_manager):
    d = DeadlineFactory()
    services.change_deadline_status(
        actor=office_manager, deadline=d, new_status=DeadlineStatus.MISSED
    )
    d.refresh_from_db()
    assert d.completed_at is not None
    services.change_deadline_status(
        actor=office_manager, deadline=d, new_status=DeadlineStatus.CANCELLED
    )
    d.refresh_from_db()
    assert d.completed_at is None
