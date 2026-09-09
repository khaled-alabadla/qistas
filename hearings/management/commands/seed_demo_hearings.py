"""Seed a few demo hearings across existing cases (spec §61). Idempotent-ish:
skips cases that already have a hearing."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import Case
from courts.models import Court
from hearings.models import Hearing, HearingType


class Command(BaseCommand):
    help = "Create demo hearings for cases that have none (idempotent)."

    def handle(self, *args, **options):
        court = Court.objects.filter(is_active=True).first()
        offsets = [3, 10, 21, -7]
        types = [
            HearingType.FIRST_SESSION,
            HearingType.PLEADING,
            HearingType.EVIDENCE,
            HearingType.VERDICT,
        ]
        created = 0
        for i, case in enumerate(Case.objects.all()[:8]):
            if case.hearings.exists():
                continue
            Hearing.objects.create(
                case=case,
                court=court,
                scheduled_at=timezone.now() + timedelta(days=offsets[i % len(offsets)]),
                hearing_type=types[i % len(types)],
                room=f"{(i % 4) + 1}",
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(f"created {created} hearing(s)"))
