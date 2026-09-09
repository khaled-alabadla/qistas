"""Seed demo tasks + deadlines across existing cases (spec §61). Idempotent-ish:
skips cases that already have tasks/deadlines."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import Case
from tasks.models import Deadline, Task, TaskPriority

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo tasks and deadlines for cases that have none (idempotent)."

    def handle(self, *args, **options):
        today = timezone.localdate()
        staff = list(User.objects.filter(is_active=True)[:5])
        task_specs = [
            ("تحضير مذكرة جوابية", TaskPriority.HIGH, -3),
            ("مراجعة ملف القضية", TaskPriority.MEDIUM, 5),
            ("تجهيز البيّنات", TaskPriority.URGENT, 2),
            ("متابعة مع الموكل", TaskPriority.LOW, 12),
        ]
        deadline_specs = [
            ("انتهاء مهلة الاستئناف", 15),
            ("تقديم اللائحة الجوابية", 7),
        ]
        t_created = d_created = 0
        for i, case in enumerate(Case.objects.all()[:6]):
            if not case.tasks.exists():
                title, prio, offset = task_specs[i % len(task_specs)]
                Task.objects.create(
                    title=title,
                    case=case,
                    client=case.client,
                    priority=prio,
                    due_date=today + timedelta(days=offset),
                    assigned_to=staff[i % len(staff)] if staff else None,
                )
                t_created += 1
            if not case.deadlines.exists():
                title, offset = deadline_specs[i % len(deadline_specs)]
                Deadline.objects.create(
                    title=title, case=case, due_date=today + timedelta(days=offset)
                )
                d_created += 1
        self.stdout.write(
            self.style.SUCCESS(f"created {t_created} task(s), {d_created} deadline(s)")
        )
