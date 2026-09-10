"""
Populate the demo inbox by running the real reminder scans over whatever seed
data exists (courts → clients → cases → hearings → tasks → contracts → finance).

Idempotent — it is exactly ``generate_notifications`` under a ``seed_demo_*``
name so it slots into the demo seed chain.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from notifications.generation import generate_all


class Command(BaseCommand):
    help = "Generate demo reminder notifications from existing seed data (idempotent)."

    def handle(self, *args, **options):
        results = generate_all()
        total = sum(results.values())
        for name, count in results.items():
            self.stdout.write(f"  {name}: {count}")
        self.stdout.write(self.style.SUCCESS(f"seeded {total} notification(s)"))
