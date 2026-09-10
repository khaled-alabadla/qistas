"""Seed a handful of demo contracts (spec §61). Idempotent-ish: skips clients
that already have a contract."""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from clients.models import Client
from contracts.models import Contract, ContractStatus, ContractType, Currency
from contracts.services import allocate_contract_number

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo contracts for clients that have none (idempotent-ish)."

    @transaction.atomic
    def handle(self, *args, **options):
        actor = User.objects.filter(is_active=True).first()
        today = timezone.localdate()
        specs = [
            ("اتفاقية تمثيل قانوني", ContractType.ENGAGEMENT, ContractStatus.ACTIVE, 15000, 400),
            ("اتفاقية أتعاب دورية", ContractType.RETAINER, ContractStatus.ACTIVE, 6000, 20),
            ("عقد استشارات قانونية", ContractType.CONSULTING, ContractStatus.DRAFT, 3500, None),
            ("اتفاقية تسوية", ContractType.SETTLEMENT, ContractStatus.EXPIRED, 25000, -90),
        ]
        created = 0
        clients = Client.objects.select_related()[:8]
        for i, client in enumerate(clients):
            if client.contracts.exists():
                continue
            title, ctype, status, value, end_offset = specs[i % len(specs)]
            end_date = today + dt.timedelta(days=end_offset) if end_offset is not None else None
            contract = Contract(
                contract_number=allocate_contract_number(),
                title=title,
                contract_type=ctype,
                client=client,
                start_date=today - dt.timedelta(days=180),
                end_date=end_date,
                value=value,
                currency=Currency.ILS,
                status=status,
                created_by=actor,
                updated_by=actor,
            )
            contract.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(f"created {created} contract(s)"))
