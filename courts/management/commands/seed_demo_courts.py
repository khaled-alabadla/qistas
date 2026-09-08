"""Realistic Palestinian courts (spec §28, §61). Idempotent."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from courts.models import Court, CourtType

DEMO = [
    ("محكمة صلح رام الله", CourtType.CONCILIATION, "رام الله"),
    ("محكمة بداية رام الله", CourtType.FIRST_INSTANCE, "رام الله"),
    ("محكمة استئناف رام الله", CourtType.APPEAL, "رام الله"),
    ("محكمة بداية نابلس", CourtType.FIRST_INSTANCE, "نابلس"),
    ("محكمة صلح الخليل", CourtType.CONCILIATION, "الخليل"),
    ("المحكمة الشرعية في بيت لحم", CourtType.SHARIA, "بيت لحم"),
    ("محكمة العدل العليا", CourtType.ADMINISTRATIVE, "رام الله"),
]


class Command(BaseCommand):
    help = "Create a handful of realistic Palestinian courts (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for name, ctype, city in DEMO:
            _obj, was_created = Court.objects.get_or_create(
                name=name, city=city, defaults={"type": ctype}
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"created {created} court(s)"))
