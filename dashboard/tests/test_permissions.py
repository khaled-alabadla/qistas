"""
Dashboard authorization — the **critical** Phase 9 regression surface.

A user only sees a domain's numbers on the dashboard if they hold that domain's
`*.view` capability. Finance is the strict one (Phase 8 — finance is not
all-staff): a **paralegal** must never see a finance figure, KPI, attention
block, financial-overview section, or a finance row in "recent activity" — and
that must hold at the *query* level, not just in the template.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from dashboard.selectors import build_dashboard
from finance.tests.factories import ExpenseFactory, issued_invoice

pytestmark = pytest.mark.django_db


FINANCE_KPI_KEYS = {"outstanding_invoices"}
FINANCE_ATTENTION_KEYS = {"overdue_invoices"}
FINANCE_ACTIONS = {
    AuditAction.FEE_AGREEMENT_CREATED,
    AuditAction.INVOICE_ISSUED,
    AuditAction.PAYMENT_RECORDED,
    AuditAction.CREDIT_NOTE_ISSUED,
    AuditAction.EXPENSE_CREATED,
}


def _seed_finance(actor):
    """Some issued invoices / overdue / a payment / an expense to make every
    finance widget non-empty."""
    from finance import services

    cl = ClientFactory()
    fresh = issued_invoice(actor=actor, client=cl, lines=[("x", 1, "1000")])
    services.record_payment(
        actor=actor,
        invoice_id=fresh.pk,
        data={"amount": Decimal("100"), "paid_on": None, "method": "cash"},
    )
    overdue = issued_invoice(actor=actor, client=cl, lines=[("y", 1, "500")])
    overdue.due_date = dt.date.today() - dt.timedelta(days=5)
    overdue.save(update_fields=["due_date"])
    ExpenseFactory(currency="ILS", amount=Decimal("75"))


# ── the critical test ──────────────────────────────────────
def test_paralegal_dashboard_has_no_finance_anywhere(paralegal, office_manager):
    _seed_finance(office_manager)
    AuditLog.objects.create(actor=office_manager, action=AuditAction.PAYMENT_RECORDED)
    AuditLog.objects.create(actor=office_manager, action=AuditAction.INVOICE_ISSUED)

    ctx = build_dashboard(paralegal)

    assert ctx["show_finance"] is False
    assert ctx["financial_overview"] == {
        "visible": False,
        "by_currency": [],
        "expenses_by_currency": [],
        "multi_currency": False,
    }
    assert not (FINANCE_KPI_KEYS & {k["key"] for k in ctx["kpis"]})
    assert not (FINANCE_ATTENTION_KEYS & {b["key"] for b in ctx["attention"]["blocks"]})
    for a in ctx["recent_activity"]:
        assert a["label"] not in {x.label for x in FINANCE_ACTIONS}


def test_finance_user_dashboard_shows_finance(office_manager):
    _seed_finance(office_manager)
    ctx = build_dashboard(office_manager)
    assert ctx["show_finance"] is True
    assert ctx["financial_overview"]["visible"] is True
    assert ctx["financial_overview"]["by_currency"]
    assert "outstanding_invoices" in {k["key"] for k in ctx["kpis"]}
    assert "overdue_invoices" in {b["key"] for b in ctx["attention"]["blocks"]}


@pytest.mark.parametrize(
    "role,finance",
    [
        ("office_manager", True),
        ("finance_clerk", True),
        ("lawyer", True),
        ("admin_clerk", True),
        ("paralegal", False),
    ],
)
def test_finance_visibility_matches_capability_matrix(role_user, role, finance):
    ctx = build_dashboard(role_user(role))
    assert ctx["show_finance"] is finance
    assert ctx["financial_overview"]["visible"] is finance


def test_no_capabilities_user_gets_a_safe_empty_dashboard(user):
    """A group-less authenticated user (no domain capabilities) sees no KPIs, no
    analytics, no case/task/finance data — never an error."""
    CaseFactory.create_batch(2)
    ExpenseFactory()
    ctx = build_dashboard(user)
    assert ctx["kpis"] == []
    assert ctx["case_analytics"] is None
    assert ctx["today_hearings"] == []
    assert ctx["upcoming_deadlines"] == []
    assert ctx["recent_cases"] == []
    assert ctx["attention"]["empty"] is True
    assert ctx["financial_overview"]["visible"] is False


def test_recent_activity_excludes_confidential_action_for_non_privileged(paralegal, office_manager):
    AuditLog.objects.create(
        actor=office_manager,
        action=AuditAction.CASE_CONFIDENTIAL_UPDATED,
        entity_type="cases.case",
        entity_id="1",
    )
    AuditLog.objects.create(
        actor=office_manager,
        action=AuditAction.CASE_CREATED,
        entity_type="cases.case",
        entity_id="1",
    )
    labels = [a["label"] for a in build_dashboard(paralegal)["recent_activity"]]
    assert AuditAction.CASE_CONFIDENTIAL_UPDATED.label not in labels


# ── HTTP surface ───────────────────────────────────────────
def test_dashboard_requires_login(client):
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_paralegal_page_renders_without_finance_markup(client, paralegal, office_manager):
    _seed_finance(office_manager)
    client.force_login(paralegal)
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 200
    assert resp.context["show_finance"] is False
    body = resp.content.decode()
    assert "الملخص المالي" not in body
    assert "الفواتير المستحقة" not in body
