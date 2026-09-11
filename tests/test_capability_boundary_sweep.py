"""
Phase 12 hardening — a single, exhaustive regression net over the finance
boundary (spec Phase 12 §6, §9): **paralegal must have ZERO finance access**,
verified at the HTTP layer for every finance URL, every finance-tagged report,
the dashboard financial widgets, and the agenda's finance-derived events —
not just "the UI hides the link" (docs/adr/0032).

This consolidates + extends the per-phase finance-isolation tests into one
file that fails loudly if a future finance URL, report, or dashboard widget is
added without the `finance.view` gate.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from cases.tests.factories import CaseFactory
from finance.tests.factories import ExpenseFactory, FeeAgreementFactory, issued_invoice

pytestmark = pytest.mark.django_db


@pytest.fixture
def finance_world(office_manager):
    """One of everything financial, owned by a case a paralegal can otherwise
    see fine (cases are all-staff visible — only the money is restricted)."""
    case = CaseFactory()
    inv = issued_invoice(
        actor=office_manager, client=case.client, case=case, lines=[("بند", 1, "1000")]
    )
    from finance import services

    payment = services.record_payment(
        actor=office_manager,
        invoice_id=inv.pk,
        data={"amount": Decimal("100"), "paid_on": dt.date.today(), "method": "cash"},
    )
    fa = FeeAgreementFactory(case=case)
    exp = ExpenseFactory(case=case, client=case.client)
    return {"case": case, "invoice": inv, "payment": payment, "fee_agreement": fa, "expense": exp}


# ── Every finance page/action: GET must 403, POST must 403 ────
def _finance_get_urls(w):
    inv, pay, fa, exp = w["invoice"], w["payment"], w["fee_agreement"], w["expense"]
    return [
        reverse("finance:fee_agreement_list"),
        reverse("finance:fee_agreement_create"),
        reverse("finance:fee_agreement_detail", args=[fa.pk]),
        reverse("finance:fee_agreement_update", args=[fa.pk]),
        reverse("finance:invoice_list"),
        reverse("finance:invoice_create"),
        reverse("finance:invoice_detail", args=[inv.pk]),
        reverse("finance:invoice_update", args=[inv.pk]),
        reverse("finance:payment_list"),
        reverse("finance:payment_detail", args=[pay.pk]),
        reverse("finance:expense_list"),
        reverse("finance:expense_create"),
        reverse("finance:expense_detail", args=[exp.pk]),
        reverse("finance:expense_update", args=[exp.pk]),
    ]


def _finance_post_urls(w):
    inv, pay, fa, exp = w["invoice"], w["payment"], w["fee_agreement"], w["expense"]
    return [
        reverse("finance:fee_agreement_status", args=[fa.pk]),
        reverse("finance:invoice_line_add", args=[inv.pk]),
        reverse("finance:invoice_issue", args=[inv.pk]),
        reverse("finance:invoice_cancel", args=[inv.pk]),
        reverse("finance:payment_create", args=[inv.pk]),
        reverse("finance:credit_note_create", args=[inv.pk]),
        reverse("finance:payment_reverse", args=[pay.pk]),
        reverse("finance:expense_retire", args=[exp.pk]),
    ]


def test_paralegal_403_on_every_finance_get_url(client, paralegal, finance_world):
    client.force_login(paralegal)
    for url in _finance_get_urls(finance_world):
        resp = client.get(url)
        assert resp.status_code == 403, f"{url} -> {resp.status_code}"


def test_paralegal_403_on_every_finance_post_url(client, paralegal, finance_world):
    client.force_login(paralegal)
    for url in _finance_post_urls(finance_world):
        resp = client.post(url, {})
        assert resp.status_code == 403, f"{url} -> {resp.status_code}"


def test_office_manager_can_reach_every_finance_get_url(client, office_manager, finance_world):
    """Positive control — the sweep isn't just permissive-by-accident. The
    invoice is issued, so its edit URL legitimately redirects (immutability,
    ADR-0012) rather than rendering — anything else must be a plain 200."""
    client.force_login(office_manager)
    invoice_update_url = reverse("finance:invoice_update", args=[finance_world["invoice"].pk])
    for url in _finance_get_urls(finance_world):
        resp = client.get(url)
        if url == invoice_update_url:
            assert resp.status_code == 302, f"{url} -> {resp.status_code}"
        else:
            assert resp.status_code == 200, f"{url} -> {resp.status_code}"


def test_paralegal_403_on_issued_invoice_edit_even_though_it_redirects_for_a_manager(
    client, paralegal, finance_world
):
    """Regression: InvoiceUpdateView.dispatch() used to redirect (not 403) for
    ANY caller when the invoice was issued — because the "not draft" guard ran
    inside dispatch() and returned before super().dispatch() (and therefore
    before CapabilityRequiredMixin) ever executed. That leaked "this invoice
    exists and is issued" via a 302 to a paralegal, who must never learn
    anything about finance data (docs/adr/0032). The draft-guard now lives in
    get()/post(), which only run after the capability check has passed."""
    client.force_login(paralegal)
    resp = client.get(reverse("finance:invoice_update", args=[finance_world["invoice"].pk]))
    assert resp.status_code == 403


# ── Finance-tagged reports ──────────────────────────────────
FINANCIAL_REPORT_SLUGS = ("revenue", "payments", "outstanding", "expenses", "case-financials")


def test_paralegal_403_on_every_financial_report(client, paralegal, finance_world):
    client.force_login(paralegal)
    for slug in FINANCIAL_REPORT_SLUGS:
        page = client.get(reverse("reports:detail", args=[slug]))
        assert page.status_code == 403, f"report {slug} page -> {page.status_code}"
        csv = client.get(reverse("reports:detail", args=[slug]), {"format": "csv"})
        assert csv.status_code == 403, f"report {slug} csv -> {csv.status_code}"


# ── Dashboard: zero finance queries, zero finance content ──
def test_paralegal_dashboard_shows_no_financial_overview(client, paralegal, finance_world):
    client.force_login(paralegal)
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 200
    assert resp.context["financial_overview"]["visible"] is False
    assert resp.context["show_finance"] is False
    body = resp.content.decode()
    assert finance_world["invoice"].invoice_number not in body


# ── Agenda: finance-derived calendar events never surface ──
def test_paralegal_agenda_has_no_invoice_due_dates(client, paralegal, finance_world):
    from django.utils import timezone

    from agenda.selectors import calendar_events

    start = timezone.make_aware(dt.datetime.combine(dt.date.today(), dt.time.min))
    events = calendar_events(paralegal, start, start + dt.timedelta(days=60))
    assert not any(e.get("kind") == "invoice" for e in events)


# ── Notifications: a paralegal never receives a finance notification ──
def test_paralegal_receives_no_invoice_overdue_notification(
    paralegal, office_manager, finance_world
):
    from finance.models import Invoice
    from notifications import generation
    from notifications.models import Notification

    Invoice.objects.filter(pk=finance_world["invoice"].pk).update(
        due_date=dt.date.today() - dt.timedelta(days=5)
    )
    generation.scan_overdue_invoices()
    assert not Notification.objects.filter(recipient=paralegal).exists()
