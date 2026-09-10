"""Financial reports — Decimal, credit notes, per-currency separation, and the
finance.view gate (spec Phase 10 §9, §10, §18)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from reports.selectors import (
    build_case_financials_report,
    build_expense_report,
    build_outstanding_report,
    build_payment_report,
    build_revenue_report,
)

pytestmark = pytest.mark.django_db

_WIDE = {
    "date_from": dt.date.today() - dt.timedelta(days=3650),
    "date_to": dt.date.today() + dt.timedelta(days=3650),
}


def _totals(result):
    """{currency: {label: Decimal}}"""
    return {block.currency: dict(block.items) for block in result.currency_totals}


# ── revenue ──────────────────────────────────────────────────────────────
def test_revenue_report_separates_currencies(office):
    r = build_revenue_report(user=office["actor"], filters=dict(_WIDE))
    t = _totals(r)
    assert set(t) == {"ILS", "USD"}
    # ILS: 1000 invoiced, 100 credited, 300 paid, 600 outstanding
    assert t["ILS"]["إجمالي الفواتير"] == Decimal("1000.00")
    assert t["ILS"]["إشعارات دائنة"] == Decimal("100.00")
    assert t["ILS"]["المحصّل"] == Decimal("300.00")
    assert t["ILS"]["المتبقي"] == Decimal("600.00")
    # USD: 500 invoiced, unpaid
    assert t["USD"]["إجمالي الفواتير"] == Decimal("500.00")
    assert t["USD"]["المتبقي"] == Decimal("500.00")


def test_revenue_report_never_sums_across_currencies(office):
    r = build_revenue_report(user=office["actor"], filters=dict(_WIDE))
    # there is no combined row/metric — only per-currency blocks
    assert all(isinstance(b.currency, str) and len(b.currency) == 3 for b in r.currency_totals)
    numbers = [amount for b in r.currency_totals for _lbl, amount in b.items]
    assert Decimal("1500.00") not in numbers  # 1000 ILS + 500 USD must never appear


def test_revenue_report_amounts_are_decimal(office):
    r = build_revenue_report(user=office["actor"], filters=dict(_WIDE))
    for row in r.rows:
        for cell in row:
            if cell.kind == "money":
                assert isinstance(cell.value, Decimal)


def test_revenue_report_currency_filter(office):
    r = build_revenue_report(user=office["actor"], filters={**_WIDE, "currency": "USD"})
    assert {row[4].value for row in r.rows} == {"USD"}
    assert set(_totals(r)) == {"USD"}


def test_revenue_report_excludes_drafts(office):
    from finance import services

    services.create_invoice(
        actor=office["actor"],
        data={"client": office["client_active"], "due_date": dt.date.today(), "currency": "ILS"},
    )
    r = build_revenue_report(user=office["actor"], filters=dict(_WIDE))
    # still only the 1 issued ILS invoice
    assert _totals(r)["ILS"]["عدد الفواتير"] == Decimal("1")


# ── payments ─────────────────────────────────────────────────────────────
def test_payment_report_net_of_reversal(office):
    from finance import services

    pmt = office["inv_ils"].payments.first()
    services.reverse_payment(
        actor=office["actor"],
        payment_id=pmt.pk,
        data={"amount": Decimal("120.00"), "reason": "شيك مرتجع"},
    )
    r = build_payment_report(user=office["actor"], filters=dict(_WIDE))
    t = _totals(r)
    assert t["ILS"]["إجمالي الدفعات"] == Decimal("300.00")
    assert t["ILS"]["استرجاعات"] == Decimal("120.00")
    assert t["ILS"]["الصافي"] == Decimal("180.00")


def test_payment_report_method_filter(office):
    r = build_payment_report(user=office["actor"], filters={**_WIDE, "method": "bank_transfer"})
    assert r.rows == []


# ── outstanding ──────────────────────────────────────────────────────────
def test_outstanding_report_open_invoices_only_per_currency(office):
    r = build_outstanding_report(user=office["actor"], filters={})
    t = _totals(r)
    assert t["ILS"]["إجمالي المتبقي"] == Decimal("600.00")
    assert t["USD"]["إجمالي المتبقي"] == Decimal("500.00")


def test_outstanding_report_aging_buckets(office):
    r = build_outstanding_report(user=office["actor"], filters={})
    t = _totals(r)
    # USD invoice due 10 days ago → 0–30 bucket
    assert t["USD"]["غير مستحقة/0–30"] == Decimal("500.00")


def test_outstanding_report_overdue_only(office):
    r = build_outstanding_report(user=office["actor"], filters={"overdue_only": True})
    # only the USD invoice has a past due_date
    assert {row[5].value for row in r.rows} == {"USD"}


# ── expenses ─────────────────────────────────────────────────────────────
def test_expense_report_per_currency_totals(office):
    r = build_expense_report(user=office["actor"], filters=dict(_WIDE))
    t = _totals(r)
    assert t["ILS"]["إجمالي المصروفات"] == Decimal("50.00")
    assert t["USD"]["إجمالي المصروفات"] == Decimal("20.00")


def test_expense_report_category_filter(office):
    r = build_expense_report(user=office["actor"], filters={**_WIDE, "category": "court_fees"})
    assert len(r.rows) == 1
    assert r.rows[0][7].value == Decimal("50.00")


# ── case financial performance ───────────────────────────────────────────
def test_case_financials_one_row_per_case_and_currency(office):
    r = build_case_financials_report(user=office["actor"], filters={})
    keys = {(row[0].value, row[3].value) for row in r.rows}
    num = office["case_open"].case_number
    assert (num, "ILS") in keys
    assert (num, "USD") in keys


def test_case_financials_credit_note_reduces_outstanding(office):
    r = build_case_financials_report(user=office["actor"], filters={})
    ils_row = next(
        row
        for row in r.rows
        if row[0].value == office["case_open"].case_number and row[3].value == "ILS"
    )
    invoiced, credited, paid, outstanding, expenses = (c.value for c in ils_row[4:9])
    assert invoiced == Decimal("1000.00")
    assert credited == Decimal("100.00")
    assert paid == Decimal("300.00")
    assert outstanding == Decimal("600.00")
    assert expenses == Decimal("50.00")


def test_case_financials_totals_never_cross_currency(office):
    r = build_case_financials_report(user=office["actor"], filters={})
    t = _totals(r)
    assert set(t) == {"ILS", "USD"}
    assert t["ILS"]["إجمالي ما فُوتر"] == Decimal("1000.00")
    assert t["USD"]["إجمالي ما فُوتر"] == Decimal("500.00")
