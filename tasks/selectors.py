"""Permission-scoped read queries for tasks and deadlines (docs/adr/0019, 0029)."""

from __future__ import annotations

import datetime as dt

from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from tasks.models import (
    Deadline,
    DeadlineStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

_TASK_SELECT = ("assigned_to", "case", "client", "created_by")
_DEADLINE_SELECT = ("case", "client", "created_by")


# ── Tasks ──────────────────────────────────────────────────
def task_list(
    *,
    user,
    query: str = "",
    status: str = "",
    priority: str = "",
    assignee_id: str = "",
    case_id: str = "",
    client_id: str = "",
    overdue_only: bool = False,
    include_closed: bool = False,
):
    qs = Task.objects.for_user(user).alive().select_related(*_TASK_SELECT)
    if query:
        qs = qs.search(query)
    if status in TaskStatus.values:
        qs = qs.filter(status=status)
    elif not include_closed:
        qs = qs.open()
    if priority in TaskPriority.values:
        qs = qs.filter(priority=priority)
    if str(assignee_id).isdigit():
        qs = qs.filter(assigned_to_id=assignee_id)
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)
    if str(client_id).isdigit():
        qs = qs.filter(client_id=client_id)
    if overdue_only:
        qs = qs.overdue()
    return qs


def case_tasks(case):
    """Every live task for ``case`` (case workspace المهام tab)."""
    return case.tasks.filter(deleted_at__isnull=True).select_related("assigned_to", "created_by")


def my_open_tasks(user):
    return (
        Task.objects.for_user(user)
        .alive()
        .assigned_to(user)
        .open()
        .select_related("case", "client")
        .order_by(F("due_date").asc(nulls_last=True), "-created_at")
    )


def overdue_tasks(user):
    return (
        Task.objects.for_user(user)
        .alive()
        .overdue()
        .select_related("assigned_to", "case", "client")
        .order_by("due_date")
    )


# ── Deadlines ──────────────────────────────────────────────
def deadline_list(
    *,
    user,
    query: str = "",
    status: str = "",
    case_id: str = "",
    client_id: str = "",
    overdue_only: bool = False,
    include_closed: bool = False,
):
    qs = Deadline.objects.for_user(user).select_related(*_DEADLINE_SELECT)
    if query:
        qs = qs.search(query)
    if status in DeadlineStatus.values:
        qs = qs.filter(status=status)
    elif not include_closed:
        qs = qs.open()
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)
    if str(client_id).isdigit():
        qs = qs.filter(client_id=client_id)
    if overdue_only:
        qs = qs.overdue()
    return qs


def case_deadlines(case):
    return case.deadlines.select_related("created_by").all()


def upcoming_deadlines(user, *, days: int = 30):
    today = timezone.localdate()
    return (
        Deadline.objects.for_user(user)
        .filter(status=DeadlineStatus.PENDING, due_date__lte=today + dt.timedelta(days=days))
        .select_related("case", "client")
        .order_by("due_date")
    )


# ── Calendar (agenda aggregator — docs/adr/0028) ────────────
def _combine(d: dt.date) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(d, dt.time.min), timezone.get_current_timezone())


def _task_event(t: Task) -> dict:
    return {
        "start": _combine(t.due_date),
        "title": t.title,
        "kind": "task",
        "all_day": True,
        "status": t.status,
        "done": t.status == TaskStatus.DONE,
        "url": reverse("tasks:detail", args=[t.pk]),
        "meta": {
            "case_title": t.case.title if t.case_id else "",
            "assignee": (t.assigned_to.get_full_name() or t.assigned_to.email)
            if t.assigned_to_id
            else "",
            "overdue": t.is_overdue,
        },
    }


def _deadline_event(d: Deadline) -> dict:
    return {
        "start": _combine(d.due_date),
        "title": d.title,
        "kind": "deadline",
        "all_day": True,
        "status": d.status,
        "done": d.status in {DeadlineStatus.MET, DeadlineStatus.MISSED},
        "url": reverse("tasks:deadline_detail", args=[d.pk]),
        "meta": {
            "case_title": d.case.title if d.case_id else "",
            "overdue": d.is_overdue,
        },
    }


def calendar_items(user, start, end) -> list[dict]:
    """Task (with a due date) + Deadline events in ``[start, end)`` for the
    agenda aggregator. Date-only → ``all_day``."""
    tasks = (
        Task.objects.for_user(user)
        .alive()
        .filter(due_date__isnull=False, due_date__gte=start.date(), due_date__lt=end.date())
        .select_related("case", "assigned_to")
    )
    deadlines = (
        Deadline.objects.for_user(user)
        .filter(due_date__gte=start.date(), due_date__lt=end.date())
        .select_related("case")
    )
    return [_task_event(t) for t in tasks] + [_deadline_event(d) for d in deadlines]
