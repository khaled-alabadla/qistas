"""
Generate the Phase 11 reminder notifications (spec §45, docs/adr/0035, ADR-0005).

Idempotent — designed to be invoked by system cron in deployment (a Phase 14
concern; the command + tests exist now). Re-running it creates nothing when the
underlying events have not changed.

    manage.py generate_notifications            # run every scan
    manage.py generate_notifications --only hearing_upcoming task_overdue
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from notifications.generation import SCANS, generate_all


class Command(BaseCommand):
    help = "Create in-app reminder notifications (hearings/tasks/deadlines/invoices/contracts)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            nargs="+",
            choices=sorted(SCANS),
            metavar="CATEGORY",
            help="Run only these scans (default: all).",
        )

    def handle(self, *args, **options):
        only = options.get("only")
        if only:
            results = {name: SCANS[name](now=None) for name in only}
        else:
            results = generate_all()

        total = sum(results.values())
        for name, count in results.items():
            self.stdout.write(f"  {name}: {count}")
        self.stdout.write(self.style.SUCCESS(f"created {total} notification(s)"))
        if total == 0 and not results:  # pragma: no cover - defensive
            raise CommandError("no scans ran")
