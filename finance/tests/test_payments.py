from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.models import CaseEventType
from cases.tests.factories import CaseFactory
from core.tests.utils import run_concurrently
from finance import services
from finance.models import InvoiceStatus, Payment, PaymentReversal
from finance.tests.factories import issued_invoice

pytestmark = pytest.mark.django_db


def _pay(actor, inv, amount, **over):
    data = {"amount": Decimal(str(amount)), "paid_on": None, "method": "cash"}
    data.update(over)
    return services.record_payment(actor=actor, invoice_id=inv.pk, data=data)


# ── normal / partial / exact ───────────────────────────────
def test_partial_then_exact_payment_walks_status(finance_clerk):
    case = CaseFactory()
    inv = issued_invoice(
        actor=finance_clerk, client=case.client, case=case, lines=[("x", 1, "1000")]
    )
    _pay(finance_clerk, inv, "400")
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PARTIALLY_PAID
    assert inv.amount_paid == Decimal("400.00")
    assert inv.outstanding == Decimal("600.00")
    _pay(finance_clerk, inv, "600")
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID
    assert inv.outstanding == Decimal("0.00")
    assert case.events.filter(event_type=CaseEventType.PAYMENT_RECORDED).count() == 2
    assert AuditLog.objects.filter(action=AuditAction.PAYMENT_RECORDED).count() == 2


def test_multiple_small_payments(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    for _ in range(4):
        _pay(finance_clerk, inv, "25")
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("100.00")
    assert inv.status == InvoiceStatus.PAID
    assert inv.payments.count() == 4


# ── overpayment (§40) ──────────────────────────────────────
def test_overpayment_rejected_and_nothing_written(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "1000")])
    with pytest.raises(ValidationError):
        _pay(finance_clerk, inv, "1000.01")
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("0.00")
    assert not Payment.objects.exists()


def test_overpayment_after_partial_rejected(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "1000")])
    _pay(finance_clerk, inv, "700")
    with pytest.raises(ValidationError):
        _pay(finance_clerk, inv, "301")
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("700.00")
    assert inv.payments.count() == 1


def test_zero_or_negative_payment_rejected(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "10")])
    for bad in ("0", "-5"):
        with pytest.raises(ValidationError):
            _pay(finance_clerk, inv, bad)


def test_cannot_pay_draft_or_cancelled(finance_clerk):
    from finance.tests.factories import InvoiceFactory

    for st in (InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED):
        inv = InvoiceFactory(status=st, total=Decimal("100"))
        with pytest.raises(ValidationError):
            _pay(finance_clerk, inv, "10")


# ── concurrency (§40) ──────────────────────────────────────
@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_payments_cannot_overpay(django_user_model):
    if connection.vendor != "postgresql":
        pytest.skip("needs real row locking (select_for_update is a no-op on SQLite)")

    from finance.tests.factories import issued_invoice as _issue

    clerk = django_user_model.objects.create_user(email="c@c.co", password="x")
    inv = _issue(actor=clerk, lines=[("x", 1, "100")])
    n = 10  # each tries to pay 20 -> only 5 can succeed (100 / 20)

    def pay():
        from django.db import connection as conn

        try:
            services.record_payment(
                actor=clerk,
                invoice_id=inv.pk,
                data={"amount": Decimal("20"), "paid_on": None, "method": "cash"},
            )
            return "ok"
        except ValidationError:
            return "rejected"
        finally:
            conn.close()

    results = run_concurrently(pay, n)
    oks = [r for r in results if r == "ok"]
    inv.refresh_from_db()
    assert len(oks) == 5
    assert inv.amount_paid == Decimal("100.00")
    assert inv.amount_paid <= inv.total  # the invariant §40 guards


def test_sequential_overpay_guard_on_sqlite(finance_clerk):
    """SQLite serializes writes, so the guard is still exercised end-to-end."""
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "50")])
    _pay(finance_clerk, inv, "50")
    with pytest.raises(ValidationError):
        _pay(finance_clerk, inv, "0.01")


# ── reversal (ADR-0012) ────────────────────────────────────
def test_reversal_reduces_amount_paid_and_status(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "1000")])
    p = _pay(finance_clerk, inv, "1000")
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID
    services.reverse_payment(
        actor=finance_clerk, payment_id=p.pk, data={"amount": Decimal("400"), "reason": "شيك مرتجع"}
    )
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("600.00")
    assert inv.status == InvoiceStatus.PARTIALLY_PAID
    assert AuditLog.objects.filter(action=AuditAction.PAYMENT_REVERSED).exists()


def test_reversal_cannot_exceed_payment(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "1000")])
    p = _pay(finance_clerk, inv, "500")
    with pytest.raises(ValidationError):
        services.reverse_payment(
            actor=finance_clerk, payment_id=p.pk, data={"amount": Decimal("600"), "reason": "x"}
        )
    assert not PaymentReversal.objects.exists()


# ── views / authz ──────────────────────────────────────────
def test_payment_view_requires_manage(client, lawyer, finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    client.force_login(lawyer)  # lawyer = finance.view only
    resp = client.post(
        reverse("finance:payment_create", args=[inv.pk]),
        {"amount": "50", "paid_on": "2026-09-10", "method": "cash"},
    )
    assert resp.status_code == 403
    assert not Payment.objects.exists()


def test_payment_view_records(client, finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    client.force_login(finance_clerk)
    resp = client.post(
        reverse("finance:payment_create", args=[inv.pk]),
        {"amount": "60", "paid_on": "2026-09-10", "method": "bank_transfer"},
    )
    assert resp.status_code == 302
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("60.00")


def test_payment_view_overpay_shows_error_not_500(client, finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    client.force_login(finance_clerk)
    resp = client.post(
        reverse("finance:payment_create", args=[inv.pk]),
        {"amount": "500", "paid_on": "2026-09-10", "method": "cash"},
        follow=True,
    )
    assert resp.status_code == 200
    assert not Payment.objects.exists()


def test_payment_detail_url_tampering_404(client, finance_clerk):
    client.force_login(finance_clerk)
    assert client.get(reverse("finance:payment_detail", args=[999999])).status_code == 404
