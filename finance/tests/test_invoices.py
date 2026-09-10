from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.models import CaseEventType
from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from finance import services
from finance.models import CreditNote, Invoice, InvoiceLineItem, InvoiceStatus
from finance.tests.factories import InvoiceFactory, issued_invoice

pytestmark = pytest.mark.django_db


def _draft(actor, **over):
    data = {
        "client": over.pop("client", None) or ClientFactory(),
        "case": over.pop("case", None),
        "due_date": None,
        "currency": "ILS",
        "tax_rate": Decimal("0"),
        "discount": Decimal("0"),
    }
    data.update(over)
    return services.create_invoice(actor=actor, data=data)


# ── server-side totals ─────────────────────────────────────
def test_totals_are_computed_server_side(finance_clerk):
    inv = _draft(finance_clerk, tax_rate=Decimal("10"), discount=Decimal("100"))
    services.add_line_item(
        actor=finance_clerk,
        invoice=inv,
        data={"description": "أ", "quantity": Decimal("2"), "unit_price": Decimal("1000")},
    )
    services.add_line_item(
        actor=finance_clerk,
        invoice=inv,
        data={"description": "ب", "quantity": Decimal("1"), "unit_price": Decimal("500.50")},
    )
    inv.refresh_from_db()
    assert inv.subtotal == Decimal("2500.50")
    assert inv.discount == Decimal("100.00")
    # (2500.50 - 100) * 10% = 240.05 ; total = 2400.50 + 240.05 = 2640.55
    assert inv.tax_amount == Decimal("240.05")
    assert inv.total == Decimal("2640.55")


def test_forged_totals_in_post_are_ignored(client, finance_clerk):
    client.force_login(finance_clerk)
    cl = ClientFactory()
    client.post(
        reverse("finance:invoice_create"),
        {
            "client": cl.pk,
            "currency": "ILS",
            "discount": "0",
            "tax_rate": "0",
            "subtotal": "999999",
            "total": "999999",
            "amount_paid": "999999",
            "invoice_number": "INV-1900-0001",
            "status": "paid",
        },
    )
    inv = Invoice.objects.get()
    assert inv.subtotal == Decimal("0.00")
    assert inv.total == Decimal("0.00")
    assert inv.amount_paid == Decimal("0.00")
    assert inv.invoice_number is None
    assert inv.status == InvoiceStatus.DRAFT


def test_discount_over_subtotal_zeroes_total_and_blocks_issue(finance_clerk):
    inv = _draft(finance_clerk)
    services.add_line_item(
        actor=finance_clerk,
        invoice=inv,
        data={"description": "x", "quantity": Decimal("1"), "unit_price": Decimal("1000")},
    )
    services.update_invoice(actor=finance_clerk, invoice=inv, data={"discount": Decimal("5000")})
    inv.refresh_from_db()
    assert inv.total == Decimal("0.00")  # never negative
    with pytest.raises(ValidationError):
        services.issue_invoice(actor=finance_clerk, invoice=inv)


# ── issuance + numbering ───────────────────────────────────
def test_issue_assigns_number_and_transitions(finance_clerk):
    case = CaseFactory()
    inv = issued_invoice(actor=finance_clerk, client=case.client, case=case)
    assert inv.invoice_number and inv.invoice_number.startswith("INV-")
    assert inv.status == InvoiceStatus.UNPAID
    assert inv.issue_date is not None
    assert case.events.filter(event_type=CaseEventType.INVOICE_ISSUED).exists()
    assert AuditLog.objects.filter(
        action=AuditAction.INVOICE_ISSUED, entity_id=str(inv.pk)
    ).exists()


def test_invoice_numbers_are_unique(finance_clerk):
    a = issued_invoice(actor=finance_clerk)
    b = issued_invoice(actor=finance_clerk)
    assert a.invoice_number != b.invoice_number


def test_cannot_issue_empty_invoice(finance_clerk):
    inv = _draft(finance_clerk)
    with pytest.raises(ValidationError):
        services.issue_invoice(actor=finance_clerk, invoice=inv)


# ── immutability (ADR-0012) ────────────────────────────────
def test_issued_invoice_cannot_be_edited(finance_clerk):
    inv = issued_invoice(actor=finance_clerk)
    with pytest.raises(ValidationError):
        services.update_invoice(actor=finance_clerk, invoice=inv, data={"notes": "x"})
    with pytest.raises(ValidationError):
        services.add_line_item(
            actor=finance_clerk,
            invoice=inv,
            data={"description": "y", "quantity": Decimal("1"), "unit_price": Decimal("1")},
        )


def test_issued_invoice_update_view_redirects(client, finance_clerk):
    inv = issued_invoice(actor=finance_clerk)
    client.force_login(finance_clerk)
    resp = client.get(reverse("finance:invoice_update", args=[inv.pk]))
    assert resp.status_code == 302  # bounced back to detail


def test_cannot_directly_cancel_issued_invoice(finance_clerk):
    inv = issued_invoice(actor=finance_clerk)
    with pytest.raises(ValidationError):
        services.cancel_invoice(actor=finance_clerk, invoice=inv)


def test_draft_can_be_cancelled(finance_clerk):
    inv = _draft(finance_clerk)
    services.cancel_invoice(actor=finance_clerk, invoice=inv)
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.CANCELLED


# ── credit notes ───────────────────────────────────────────
def test_full_credit_note_voids_invoice(finance_clerk):
    case = CaseFactory()
    inv = issued_invoice(
        actor=finance_clerk, client=case.client, case=case, lines=[("x", 1, "1000")]
    )
    services.issue_credit_note(
        actor=finance_clerk, invoice_id=inv.pk, data={"amount": Decimal("1000"), "reason": "خطأ"}
    )
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.CANCELLED
    assert case.events.filter(event_type=CaseEventType.CREDIT_NOTE_ISSUED).exists()


def test_partial_credit_note_reduces_outstanding(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "1000")])
    services.issue_credit_note(
        actor=finance_clerk, invoice_id=inv.pk, data={"amount": Decimal("300"), "reason": "خصم"}
    )
    inv.refresh_from_db()
    assert inv.credited_total == Decimal("700.00")
    assert inv.outstanding == Decimal("700.00")


def test_credit_note_cannot_exceed_total(finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "1000")])
    with pytest.raises(ValidationError):
        services.issue_credit_note(
            actor=finance_clerk, invoice_id=inv.pk, data={"amount": Decimal("2000"), "reason": "x"}
        )
    assert not CreditNote.objects.exists()


def test_credit_note_only_on_issued(finance_clerk):
    inv = _draft(finance_clerk)
    with pytest.raises(ValidationError):
        services.issue_credit_note(
            actor=finance_clerk, invoice_id=inv.pk, data={"amount": Decimal("1"), "reason": "x"}
        )


# ── views / authz ──────────────────────────────────────────
def test_list_hides_cancelled_by_default(client, finance_clerk):
    issued_invoice(actor=finance_clerk)
    d = InvoiceFactory(status=InvoiceStatus.CANCELLED)
    client.force_login(finance_clerk)
    assert client.get(reverse("finance:invoice_list")).context["total_count"] == 1
    assert d not in client.get(reverse("finance:invoice_list")).context["invoices"]


def test_line_add_remove_via_view(client, finance_clerk):
    inv = _draft(finance_clerk)
    client.force_login(finance_clerk)
    client.post(
        reverse("finance:invoice_line_add", args=[inv.pk]),
        {"description": "بند", "quantity": "2", "unit_price": "750"},
    )
    line = InvoiceLineItem.objects.get()
    inv.refresh_from_db()
    assert inv.subtotal == Decimal("1500.00")
    client.post(reverse("finance:invoice_line_remove", args=[inv.pk, line.pk]))
    inv.refresh_from_db()
    assert inv.subtotal == Decimal("0.00")


def test_line_remove_rejects_foreign_line(client, finance_clerk):
    inv_a = _draft(finance_clerk)
    inv_b = _draft(finance_clerk)
    services.add_line_item(
        actor=finance_clerk,
        invoice=inv_b,
        data={"description": "x", "quantity": Decimal("1"), "unit_price": Decimal("1")},
    )
    other_line = inv_b.line_items.get()
    client.force_login(finance_clerk)
    resp = client.post(reverse("finance:invoice_line_remove", args=[inv_a.pk, other_line.pk]))
    assert resp.status_code == 404
    assert inv_b.line_items.exists()


def test_url_tampering_returns_404(client, finance_clerk):
    client.force_login(finance_clerk)
    assert client.get(reverse("finance:invoice_detail", args=[123456])).status_code == 404


def test_invoice_list_query_count_is_flat(client, finance_clerk):
    """Totals / outstanding come from a `with_balances()` annotation — the query
    count must not grow with the number of invoices (the pre-existing per-request
    `can()` overhead is constant and out of scope, ADR-0010)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def build(n):
        for _ in range(n):
            inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "1000")])
            services.record_payment(
                actor=finance_clerk,
                invoice_id=inv.pk,
                data={"amount": Decimal("100"), "paid_on": None, "method": "cash"},
            )
            services.issue_credit_note(
                actor=finance_clerk,
                invoice_id=inv.pk,
                data={"amount": Decimal("50"), "reason": "x"},
            )

    client.force_login(finance_clerk)
    build(3)
    with CaptureQueriesContext(connection) as few:
        client.get(reverse("finance:invoice_list"))
    build(6)  # 9 total
    with CaptureQueriesContext(connection) as many:
        client.get(reverse("finance:invoice_list"))
    assert len(many.captured_queries) == len(few.captured_queries)


# ── code-review follow-ups ─────────────────────────────────
def test_cannot_issue_an_already_issued_invoice(finance_clerk):
    inv = issued_invoice(actor=finance_clerk)
    with pytest.raises(ValidationError):
        services.issue_invoice(actor=finance_clerk, invoice=inv)
    # only one number / audit row / case event
    assert Invoice.objects.filter(invoice_number=inv.invoice_number).count() == 1
    assert (
        AuditLog.objects.filter(action=AuditAction.INVOICE_ISSUED, entity_id=str(inv.pk)).count()
        == 1
    )


def test_invoice_rejects_fee_agreement_from_a_different_case(finance_clerk):
    from finance.tests.factories import FeeAgreementFactory

    case_a = CaseFactory()
    fa_other = FeeAgreementFactory()  # its own (different) case
    with pytest.raises(ValidationError):
        _draft(finance_clerk, client=case_a.client, case=case_a, fee_agreement=fa_other)


def test_clearing_discount_via_update_zeroes_it(finance_clerk):
    inv = _draft(finance_clerk, discount=Decimal("300"))
    services.add_line_item(
        actor=finance_clerk,
        invoice=inv,
        data={"description": "x", "quantity": Decimal("1"), "unit_price": Decimal("1000")},
    )
    services.update_invoice(actor=finance_clerk, invoice=inv, data={"discount": None})
    inv.refresh_from_db()
    assert inv.discount == Decimal("0.00")
    assert inv.total == Decimal("1000.00")


def test_client_financials_per_currency_and_credit_note_aware(finance_clerk):
    from finance.selectors import client_financials

    cl = ClientFactory()
    ils = issued_invoice(actor=finance_clerk, client=cl, lines=[("x", 1, "1000")])
    services.issue_credit_note(
        actor=finance_clerk, invoice_id=ils.pk, data={"amount": Decimal("200"), "reason": "x"}
    )
    services.record_payment(
        actor=finance_clerk,
        invoice_id=ils.pk,
        data={"amount": Decimal("300"), "paid_on": None, "method": "cash"},
    )
    usd = _draft(finance_clerk, client=cl, currency="USD")
    services.add_line_item(
        actor=finance_clerk,
        invoice=usd,
        data={"description": "y", "quantity": Decimal("1"), "unit_price": Decimal("500")},
    )
    services.issue_invoice(actor=finance_clerk, invoice=usd)

    fin = client_financials(cl)
    assert fin["multi_currency"] is True
    rows = {r["currency"]: r for r in fin["by_currency"]}
    # ILS: invoiced 1000, credited 200, paid 300 -> outstanding 500
    assert rows["ILS"]["outstanding"] == Decimal("500.00")
    assert rows["ILS"]["credited"] == Decimal("200.00")
    # USD kept entirely separate
    assert rows["USD"]["invoiced"] == Decimal("500.00")
    assert rows["USD"]["outstanding"] == Decimal("500.00")
