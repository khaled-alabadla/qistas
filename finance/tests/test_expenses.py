import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.tests.factories import CaseFactory
from finance import services
from finance.models import Expense, ExpenseCategory
from finance.tests.factories import ExpenseFactory

pytestmark = pytest.mark.django_db


def test_create_allocates_reference_and_audits(finance_clerk):
    exp = services.create_expense(
        actor=finance_clerk,
        data={
            "description": "رسوم دعوى",
            "amount": Decimal("350"),
            "currency": "ILS",
            "category": ExpenseCategory.COURT_FEES,
            "spent_on": dt.date.today(),
        },
    )
    assert exp.reference.startswith("EXP-")
    assert exp.created_by == finance_clerk
    assert AuditLog.objects.filter(
        action=AuditAction.EXPENSE_CREATED, entity_id=str(exp.pk)
    ).exists()


def test_expense_is_not_added_to_any_invoice_total(finance_clerk):
    """An expense is money out — it never touches invoice / fee totals (ADR-0013)."""
    case = CaseFactory()
    ExpenseFactory(case=case, amount=Decimal("999"), currency="ILS")
    from finance.selectors import case_financials

    fin = case_financials(case)
    assert fin["by_currency"] == []  # no issued invoices → expense did not inflate anything
    assert fin["expenses_by_currency"] == [{"currency": "ILS", "total": Decimal("999.00")}]


def test_negative_amount_rejected(finance_clerk):
    with pytest.raises(ValidationError):
        services.create_expense(
            actor=finance_clerk,
            data={
                "description": "x",
                "amount": Decimal("-1"),
                "category": "other",
                "spent_on": dt.date.today(),
            },
        )


def test_update_and_audit(finance_clerk):
    exp = ExpenseFactory(amount=Decimal("100"))
    services.update_expense(actor=finance_clerk, expense=exp, data={"amount": Decimal("120")})
    exp.refresh_from_db()
    assert exp.amount == Decimal("120.00")
    assert AuditLog.objects.filter(action=AuditAction.EXPENSE_UPDATED).exists()


def test_retire_is_soft_and_idempotent(finance_clerk):
    exp = ExpenseFactory()
    services.retire_expense(actor=finance_clerk, expense=exp)
    exp.refresh_from_db()
    assert exp.deleted_at is not None and exp.deleted_by == finance_clerk
    assert Expense.objects.filter(pk=exp.pk).exists()  # row kept
    assert exp not in Expense.objects.alive()
    services.retire_expense(actor=finance_clerk, expense=exp)
    assert AuditLog.objects.filter(action=AuditAction.EXPENSE_RETIRED).count() == 1


def test_cannot_edit_retired(finance_clerk):
    exp = ExpenseFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    with pytest.raises(ValidationError):
        services.update_expense(actor=finance_clerk, expense=exp, data={"amount": Decimal("1")})


# ── views ──────────────────────────────────────────────────
def test_list_hides_retired(client, finance_clerk):
    ExpenseFactory()
    ExpenseFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    client.force_login(finance_clerk)
    assert client.get(reverse("finance:expense_list")).context["total_count"] == 1


def test_create_view(client, finance_clerk):
    client.force_login(finance_clerk)
    resp = client.post(
        reverse("finance:expense_create"),
        {
            "description": "سفر",
            "amount": "200",
            "currency": "ILS",
            "category": "travel",
            "spent_on": "2026-09-01",
        },
    )
    assert resp.status_code == 302
    assert Expense.objects.count() == 1


def test_create_view_forbidden_for_admin_clerk(client, admin_clerk):
    client.force_login(admin_clerk)  # finance.view only
    assert client.get(reverse("finance:expense_create")).status_code == 403


def test_retire_view_post_only(client, finance_clerk):
    exp = ExpenseFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("finance:expense_retire", args=[exp.pk])).status_code == 405
