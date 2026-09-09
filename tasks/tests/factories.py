from __future__ import annotations

import datetime as dt

import factory

from tasks.models import Deadline, DeadlineStatus, Task, TaskPriority, TaskStatus


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Task

    title = factory.Sequence(lambda n: f"مهمة اختبار {n}")
    priority = TaskPriority.MEDIUM
    status = TaskStatus.NEW


class DeadlineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Deadline

    title = factory.Sequence(lambda n: f"موعد نهائي {n}")
    status = DeadlineStatus.PENDING
    due_date = factory.LazyFunction(lambda: dt.date.today() + dt.timedelta(days=14))
