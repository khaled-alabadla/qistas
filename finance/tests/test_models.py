import datetime as dt
from decimal import Decimal
from importlib import import_module

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from cases.tests.factories import CaseFactory
from finance.models import (
    EXPENSE_SEARCH_FIELDS,
    FEE_AGREEMENT_SEARCH_FIELDS,
    INVOICE_SEARCH_FIELDS,
    CreditNote,
    Expense,
    FeeAgreement,
    FeeType,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    Payment,
    PaymentReversal,
)
from finance.tests.factories import (
    FeeAgreementFactory,
    InvoiceFactory,
    InvoiceLineItemFactory,
)

pytestmark = pytest.mark.django_db


# ── money / Decimal ────────────────────────────────────────
def test_money_fields_are_decimal():
    inv = InvoiceFactory()
    assert isinstance(inv.total, Decimal)
    assert isinstance(inv.amount_paid, Decimal)
    li = InvoiceLineItemFactory(quantity=Decimal("3"), unit_price=Decimal("1.115"))
    assert li.compute_total() == Decimal("3.35")  # 3.345 -> half-up 2dp


def test_quantize_half_up():
    from core.money import quantize

    assert quantize(Decimal("0.005")) == Decimal("0.01")
    assert quantize(Decimal("2.344")) == Decimal("2.34")


# ── constraints ────────────────────────────────────────────
def test_invoice_no_overpayment_db_constraint():
    inv = InvoiceFactory(status=InvoiceStatus.UNPAID, total=Decimal("100.00"))
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal("150.00"))


def test_invoice_negative_total_rejected():
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.create(
            client=CaseFactory().client, total=Decimal("-1.00"), status=InvoiceStatus.DRAFT
        )


def test_line_item_quantity_must_be_positive():
    inv = InvoiceFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        InvoiceLineItem.objects.create(
            invoice=inv, description="x", quantity=Decimal("0"), unit_price=Decimal("1")
        )


def test_payment_amount_must_be_positive():
    inv = InvoiceFactory(status=InvoiceStatus.UNPAID, total=Decimal("10"))
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(
            reference="PMT-x", invoice=inv, amount=Decimal("0"), paid_on=dt.date.today()
        )


def test_fee_contingency_percent_range_constraint():
    with pytest.raises(IntegrityError), transaction.atomic():
        FeeAgreement.objects.create(
            reference="FA-x",
            case=CaseFactory(),
            fee_type=FeeType.CONTINGENCY,
            contingency_percent=Decimal("150"),
        )


def test_expense_amount_must_be_positive():
    with pytest.raises(IntegrityError), transaction.atomic():
        Expense.objects.create(
            reference="EXP-x", description="x", amount=Decimal("0"), spent_on=dt.date.today()
        )


# ── clean() ────────────────────────────────────────────────
def test_fee_agreement_clean_requires_field_for_type():
    fa = FeeAgreementFactory.build(fee_type=FeeType.HOURLY, hourly_rate=None, fixed_amount=None)
    with pytest.raises(ValidationError):
        fa.clean()


def test_fee_agreement_clean_end_before_start():
    fa = FeeAgreementFactory.build(
        start_date=dt.date.today(), end_date=dt.date.today() - dt.timedelta(days=1)
    )
    with pytest.raises(ValidationError):
        fa.clean()


# ── uniqueness ─────────────────────────────────────────────
def test_reference_uniqueness():
    FeeAgreementFactory(reference="FA-2026-5000")
    with pytest.raises(IntegrityError), transaction.atomic():
        FeeAgreementFactory(reference="FA-2026-5000")


def test_invoice_number_unique_but_nullable_for_drafts():
    InvoiceFactory()
    InvoiceFactory()  # two drafts, both invoice_number=None -> OK
    assert Invoice.objects.filter(invoice_number__isnull=True).count() == 2


# ── relationships / on_delete ──────────────────────────────
def test_line_items_cascade_with_invoice():
    inv = InvoiceFactory()
    InvoiceLineItemFactory(invoice=inv)
    inv_pk = inv.pk
    inv.delete()  # hard delete only reachable in tests/admin-off; verifies CASCADE
    assert not InvoiceLineItem.objects.filter(invoice_id=inv_pk).exists()


def test_payment_protects_invoice():
    inv = InvoiceFactory(status=InvoiceStatus.UNPAID, total=Decimal("10"))
    Payment.objects.create(
        reference="PMT-z", invoice=inv, amount=Decimal("5"), paid_on=dt.date.today()
    )
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        inv.delete()


# ── permissions ────────────────────────────────────────────
@pytest.mark.parametrize(
    "model,expected",
    [
        (FeeAgreement, {"add", "change", "view"}),
        (Invoice, {"add", "change", "view"}),
        (Payment, {"add", "view"}),
        (PaymentReversal, {"add", "view"}),
        (CreditNote, {"add", "view"}),
        (Expense, {"add", "change", "view"}),
    ],
)
def test_default_permissions_no_delete(model, expected):
    assert set(model._meta.default_permissions) == expected
    assert "delete" not in model._meta.default_permissions


# ── trigram columns ────────────────────────────────────────
def test_trgm_columns_cover_search_fields():
    mod = import_module("finance.migrations.0002_finance_search_indexes")
    assert tuple(sorted(mod.FEE_AGREEMENT_TRGM_COLUMNS)) == tuple(
        sorted(FEE_AGREEMENT_SEARCH_FIELDS)
    )
    assert tuple(sorted(mod.INVOICE_TRGM_COLUMNS)) == tuple(sorted(INVOICE_SEARCH_FIELDS))
    assert tuple(sorted(mod.EXPENSE_TRGM_COLUMNS)) == tuple(sorted(EXPENSE_SEARCH_FIELDS))
