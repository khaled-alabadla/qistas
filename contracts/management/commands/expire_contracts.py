"""
Flip ``active`` contracts whose ``end_date`` has passed to ``expired``
(docs/adr/0005, architecture §12, docs/adr/0031).

Idempotent — designed to be invoked by system cron (a Phase 14 deployment
concern; the command exists + is tested now). Audited; one ``CaseEvent`` per
case-linked row.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from contracts.services import expire_due_contracts


class Command(BaseCommand):
    help = "Mark active contracts past their end_date as expired (idempotent)."

    def handle(self, *args, **options):
        count = expire_due_contracts()
        self.stdout.write(self.style.SUCCESS(f"expired {count} contract(s)"))
