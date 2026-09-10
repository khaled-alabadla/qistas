from __future__ import annotations

import datetime as dt
from decimal import Decimal

import factory

from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from finance.models import (
    Expense,
    ExpenseCategory,
    FeeAgreement,
    FeeAgreementStatus,
    FeeType,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
)


class FeeAgreementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeeAgreement

    reference = factory.Sequence(lambda n: f"FA-2026-{n + 1:04d}")
    case = factory.SubFactory(CaseFactory)
    fee_type = FeeType.FIXED
    fixed_amount = Decimal("10000.00")
    status = FeeAgreementStatus.DRAFT


class InvoiceFactory(factory.django.DjangoModelFactory):
    """A DRAFT invoice with no line items. Use ``issued_invoice`` for a real one."""

    class Meta:
        model = Invoice

    client = factory.SubFactory(ClientFactory)
    case = factory.SubFactory(CaseFactory)
    status = InvoiceStatus.DRAFT
    currency = "ILS"
    due_date = factory.LazyFunction(lambda: dt.date.today() + dt.timedelta(days=30))


class InvoiceLineItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InvoiceLineItem

    invoice = factory.SubFactory(InvoiceFactory)
    description = factory.Sequence(lambda n: f"بند {n}")
    quantity = Decimal("1.00")
    unit_price = Decimal("1000.00")
    line_total = Decimal("1000.00")


class ExpenseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Expense

    reference = factory.Sequence(lambda n: f"EXP-2026-{n + 1:04d}")
    description = factory.Sequence(lambda n: f"مصروف {n}")
    amount = Decimal("500.00")
    currency = "ILS"
    category = ExpenseCategory.OTHER
    spent_on = factory.LazyFunction(dt.date.today)


def issued_invoice(
    *, actor, client=None, case=None, lines=((("أتعاب", 1, "5000.00")),), tax_rate="0"
):
    """Build + issue a real invoice through the services (the only correct path)."""
    from finance import services

    inv = services.create_invoice(
        actor=actor,
        data={
            "client": client or ClientFactory(),
            "case": case,
            "due_date": dt.date.today() + dt.timedelta(days=30),
            "currency": "ILS",
            "tax_rate": Decimal(tax_rate),
        },
    )
    for desc, qty, price in lines:
        services.add_line_item(
            actor=actor,
            invoice=inv,
            data={"description": desc, "quantity": Decimal(str(qty)), "unit_price": Decimal(price)},
        )
    return services.issue_invoice(actor=actor, invoice=inv)
