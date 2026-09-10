"""Seed a little demo finance data (spec §61). Idempotent-ish: skips cases /
clients that already have finance records."""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cases.models import Case
from finance import services
from finance.models import ExpenseCategory, FeeType

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo fee agreements, invoices, payments and expenses (idempotent-ish)."

    @transaction.atomic
    def handle(self, *args, **options):
        actor = User.objects.filter(is_active=True).first()
        today = timezone.localdate()
        made = {"fee": 0, "invoice": 0, "payment": 0, "expense": 0}

        for i, case in enumerate(Case.objects.select_related("client")[:5]):
            if case.fee_agreements.exists() or case.invoices.exists():
                continue
            services.create_fee_agreement(
                actor=actor,
                data={
                    "case": case,
                    "fee_type": FeeType.FIXED,
                    "fixed_amount": 12000,
                    "currency": "ILS",
                    "agreed_on": today - dt.timedelta(days=60),
                    "description": "اتفاقية أتعاب تجريبية",
                },
            )
            made["fee"] += 1

            invoice = services.create_invoice(
                actor=actor,
                data={
                    "client": case.client,
                    "case": case,
                    "due_date": today + dt.timedelta(days=30),
                    "currency": "ILS",
                    "tax_rate": 16,
                },
            )
            services.add_line_item(
                actor=actor,
                invoice=invoice,
                data={"description": "أتعاب المرحلة الأولى", "quantity": 1, "unit_price": 8000},
            )
            services.add_line_item(
                actor=actor,
                invoice=invoice,
                data={"description": "رسوم ومصاريف", "quantity": 1, "unit_price": 1500},
            )
            services.issue_invoice(actor=actor, invoice=invoice)
            made["invoice"] += 1

            if i % 2 == 0:
                invoice.refresh_from_db()
                services.record_payment(
                    actor=actor,
                    invoice_id=invoice.pk,
                    data={
                        "amount": invoice.outstanding / 2,
                        "paid_on": today,
                        "method": "bank_transfer",
                    },
                )
                made["payment"] += 1

            services.create_expense(
                actor=actor,
                data={
                    "description": "رسوم تقديم دعوى",
                    "amount": 350,
                    "currency": "ILS",
                    "category": ExpenseCategory.COURT_FEES,
                    "spent_on": today - dt.timedelta(days=10),
                    "case": case,
                    "client": case.client,
                },
            )
            made["expense"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"fee agreements: {made['fee']} · invoices: {made['invoice']} · "
                f"payments: {made['payment']} · expenses: {made['expense']}"
            )
        )
