"""Demo cases for a fresh dev database (spec §61). Idempotent-ish: skips if any
case already exists. Requires clients + courts + case types to be present."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from cases.models import Case, CasePriority, CaseType
from cases.services import create_case
from clients.models import Client
from courts.models import Court

DEMO = [
    ("نزاع عقد إيجار تجاري", "تجارية", CasePriority.HIGH, "conciliation"),
    ("مطالبة بأجور عمالية", "عمالية", CasePriority.MEDIUM, "first_instance"),
    ("قضية أحوال شخصية - نفقة", "أحوال شخصية", CasePriority.URGENT, "sharia"),
    ("تعويض عن حادث سير", "مدنية", CasePriority.MEDIUM, "first_instance"),
]


class Command(BaseCommand):
    help = "Create a few demo cases (needs clients + courts; skips if cases exist)."

    def handle(self, *args, **options):
        if Case.objects.exists():
            self.stdout.write("cases already present — skipping.")
            return

        client = Client.objects.order_by("pk").first()
        if client is None:
            self.stderr.write(self.style.ERROR("no clients — run seed_demo_clients first."))
            return

        created = 0
        for title, type_name, priority, court_type in DEMO:
            ctype, _ = CaseType.objects.get_or_create(name=type_name)
            court = Court.objects.filter(type=court_type).first()
            create_case(
                actor=None,
                data={
                    "title": title,
                    "type": ctype,
                    "client": client,
                    "priority": priority,
                    "court": court,
                },
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(f"created {created} demo case(s)"))
