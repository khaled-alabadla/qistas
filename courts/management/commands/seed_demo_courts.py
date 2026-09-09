"""Realistic Palestinian courts (spec §28, §61). Idempotent."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from courts.models import Court, CourtType

DEMO = [
    ("محكمة صلح رام الله", CourtType.CONCILIATION, "رام الله", "المصيون", "02-2985555"),
    ("محكمة بداية رام الله", CourtType.FIRST_INSTANCE, "رام الله", "المصيون", "02-2985500"),
    ("محكمة استئناف رام الله", CourtType.APPEAL, "رام الله", "", "02-2984000"),
    ("محكمة بداية نابلس", CourtType.FIRST_INSTANCE, "نابلس", "", "09-2371000"),
    ("محكمة صلح الخليل", CourtType.CONCILIATION, "الخليل", "", "02-2221000"),
    ("المحكمة الشرعية في بيت لحم", CourtType.SHARIA, "بيت لحم", "", "02-2741000"),
    ("محكمة العدل العليا", CourtType.ADMINISTRATIVE, "رام الله", "", "02-2986000"),
]


class Command(BaseCommand):
    help = "Create a handful of realistic Palestinian courts (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for name, ctype, city, department, phone in DEMO:
            _obj, was_created = Court.objects.get_or_create(
                name=name,
                city=city,
                defaults={"type": ctype, "department": department, "phone": phone},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"created {created} court(s)"))
