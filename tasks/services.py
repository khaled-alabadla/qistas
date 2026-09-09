"""
Transactional writes for tasks and deadlines (docs/adr/0018, 0029).

Every mutation writes an ``audit.AuditLog`` event; a **case-linked** row also
records a ``CaseEvent`` on the case timeline (spec §26). Tasks soft-delete
(``deleted_at``); deadlines are never deleted — they are cancelled (docs/adr/0022).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from audit.events import log_event
from audit.models import AuditAction
from cases.models import CaseEventType
from cases.services import record_case_event
from tasks.models import Deadline, DeadlineStatus, Task, TaskStatus

TASK_EDITABLE = ("title", "description", "assigned_to", "case", "client", "priority", "due_date")
DEADLINE_EDITABLE = ("title", "description", "case", "client", "due_date")


def _who(user) -> str:
    if user is None:
        return "—"
    return user.get_full_name() or user.email


def _label(model, field, value) -> str:
    try:
        return dict(model._meta.get_field(field).choices)[value]
    except Exception:
        return str(value)


# ── Task ───────────────────────────────────────────────────
@transaction.atomic
def create_task(*, actor, data: dict, request=None) -> Task:
    task = Task(**data)
    task.created_by = actor
    task.updated_by = actor
    if task.status == TaskStatus.DONE:
        task.completed_at = timezone.now()
    task.full_clean(exclude=["created_by", "updated_by"])
    task.save()
    if task.case_id:
        record_case_event(
            task.case,
            CaseEventType.TASK_ADDED,
            f"مهمة جديدة: {task.title}",
            actor=actor,
            task_id=task.pk,
        )
    log_event(request, AuditAction.TASK_CREATED, actor=actor, obj=task)
    return task


@transaction.atomic
def update_task(*, actor, task: Task, data: dict, request=None) -> Task:
    data = {k: v for k, v in data.items() if k in TASK_EDITABLE}
    stored = Task.objects.select_related("assigned_to", "case", "client").get(pk=task.pk)
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return task
    for field, value in data.items():
        setattr(task, field, value)
    task.updated_by = actor
    task.full_clean(exclude=["created_by", "updated_by"])
    task.save()
    log_event(
        request,
        AuditAction.TASK_UPDATED,
        actor=actor,
        obj=task,
        changes={"fields": sorted(changed)},
    )
    return task


@transaction.atomic
def change_task_status(*, actor, task: Task, new_status: str, request=None) -> Task:
    if task.status == new_status:
        return task
    previous = task.status
    task.status = new_status
    task.completed_at = timezone.now() if new_status == TaskStatus.DONE else None
    task.updated_by = actor
    task.save(update_fields=["status", "completed_at", "updated_by", "updated_at"])

    if task.case_id:
        record_case_event(
            task.case,
            CaseEventType.TASK_STATUS_CHANGED,
            f"مهمة «{task.title}»: {_label(Task, 'status', previous)} ← "
            f"{_label(Task, 'status', new_status)}",
            actor=actor,
            task_id=task.pk,
        )
    log_event(
        request,
        AuditAction.TASK_STATUS_CHANGED,
        actor=actor,
        obj=task,
        changes={"status": [previous, new_status]},
    )
    return task


@transaction.atomic
def delete_task(*, actor, task: Task, request=None) -> Task:
    if task.deleted_at is not None:
        return task
    task.deleted_at = timezone.now()
    task.deleted_by = actor
    task.save(update_fields=["deleted_at", "deleted_by"])
    if task.case_id:
        record_case_event(
            task.case,
            CaseEventType.TASK_REMOVED,
            f"حُذفت المهمة: {task.title}",
            actor=actor,
            task_id=task.pk,
        )
    log_event(request, AuditAction.TASK_DELETED, actor=actor, obj=task)
    return task


# ── Deadline ───────────────────────────────────────────────
@transaction.atomic
def create_deadline(*, actor, data: dict, request=None) -> Deadline:
    deadline = Deadline(**data)
    deadline.created_by = actor
    deadline.updated_by = actor
    deadline.full_clean(exclude=["created_by", "updated_by"])
    deadline.save()
    if deadline.case_id:
        record_case_event(
            deadline.case,
            CaseEventType.DEADLINE_ADDED,
            f"موعد نهائي: {deadline.title} ({deadline.due_date})",
            actor=actor,
            deadline_id=deadline.pk,
        )
    log_event(request, AuditAction.DEADLINE_CREATED, actor=actor, obj=deadline)
    return deadline


@transaction.atomic
def update_deadline(*, actor, deadline: Deadline, data: dict, request=None) -> Deadline:
    data = {k: v for k, v in data.items() if k in DEADLINE_EDITABLE}
    stored = Deadline.objects.select_related("case", "client").get(pk=deadline.pk)
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return deadline
    for field, value in data.items():
        setattr(deadline, field, value)
    deadline.updated_by = actor
    deadline.full_clean(exclude=["created_by", "updated_by"])
    deadline.save()
    log_event(
        request,
        AuditAction.DEADLINE_UPDATED,
        actor=actor,
        obj=deadline,
        changes={"fields": sorted(changed)},
    )
    return deadline


@transaction.atomic
def change_deadline_status(*, actor, deadline: Deadline, new_status: str, request=None) -> Deadline:
    if deadline.status == new_status:
        return deadline
    previous = deadline.status
    deadline.status = new_status
    deadline.completed_at = (
        timezone.now() if new_status in {DeadlineStatus.MET, DeadlineStatus.MISSED} else None
    )
    deadline.updated_by = actor
    deadline.save(update_fields=["status", "completed_at", "updated_by", "updated_at"])

    if deadline.case_id:
        record_case_event(
            deadline.case,
            CaseEventType.DEADLINE_STATUS_CHANGED,
            f"موعد نهائي «{deadline.title}»: {_label(Deadline, 'status', previous)} ← "
            f"{_label(Deadline, 'status', new_status)}",
            actor=actor,
            deadline_id=deadline.pk,
        )
    log_event(
        request,
        AuditAction.DEADLINE_STATUS_CHANGED,
        actor=actor,
        obj=deadline,
        changes={"status": [previous, new_status]},
    )
    return deadline
