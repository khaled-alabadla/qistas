"""Shared builders for the reports test-suite."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from cases.models import CasePriority, CaseStatus
from cases.tests.factories import CaseFactory, CaseTypeFactory
from clients.tests.factories import ClientFactory
from courts.tests.factories import CourtFactory
from finance import services
from finance.models import ExpenseCategory
from finance.tests.factories import ExpenseFactory, issued_invoice
from hearings.models import HearingStatus
from hearings.tests.factories import HearingFactory
from tasks.models import DeadlineStatus, TaskStatus
from tasks.tests.factories import DeadlineFactory, TaskFactory

ALL_REPORT_SLUGS = [
    "cases",
    "clients",
    "hearings",
    "tasks",
    "deadlines",
    "revenue",
    "payments",
    "outstanding",
    "expenses",
    "case-financials",
]
FINANCIAL_SLUGS = ["revenue", "payments", "outstanding", "expenses", "case-financials"]
GENERAL_SLUGS = ["cases", "clients", "hearings", "tasks", "deadlines"]


@pytest.fixture
def office(db, office_manager):
    """A small but complete office: clients, cases, hearings, tasks, deadlines,
    and — in two currencies — invoices, a payment, a credit note and expenses."""
    actor = office_manager
    court = CourtFactory(name="محكمة صلح رام الله")
    ctype = CaseTypeFactory(name="مدني")

    c_active = ClientFactory(full_name="سميرة عوض")
    c_prospect = ClientFactory(full_name="خالد حدّاد")
    from clients.models import ClientStatus

    c_prospect.status = ClientStatus.PROSPECT
    c_prospect.save(update_fields=["status"])

    case_open = CaseFactory(
        client=c_active,
        type=ctype,
        court=court,
        assigned_lawyer=actor,
        status=CaseStatus.IN_PROGRESS,
        priority=CasePriority.URGENT,
    )
    case_closed = CaseFactory(client=c_active, type=ctype, status=CaseStatus.CLOSED)

    HearingFactory(case=case_open, court=court, lawyer=actor, status=HearingStatus.SCHEDULED)
    HearingFactory(
        case=case_open,
        court=court,
        status=HearingStatus.HELD,
        scheduled_at=_days(-10),
    )

    TaskFactory(case=case_open, assigned_to=actor, status=TaskStatus.NEW, due_date=_date(-3))
    TaskFactory(case=case_open, assigned_to=actor, status=TaskStatus.DONE, due_date=_date(-30))
    DeadlineFactory(case=case_open, status=DeadlineStatus.PENDING, due_date=_date(-2))
    DeadlineFactory(case=case_open, status=DeadlineStatus.MET, due_date=_date(-20))

    # Finance — ILS invoice with a payment + a credit note
    inv_ils = issued_invoice(
        actor=actor, client=c_active, case=case_open, lines=[("أتعاب", 1, "1000.00")]
    )
    services.record_payment(
        actor=actor,
        invoice_id=inv_ils.pk,
        data={"amount": Decimal("300.00"), "paid_on": dt.date.today(), "method": "cash"},
    )
    services.issue_credit_note(
        actor=actor,
        invoice_id=inv_ils.pk,
        data={"amount": Decimal("100.00"), "reason": "خصم متفق عليه"},
    )
    # USD invoice, unpaid + overdue
    inv_usd = _issue_usd(actor, c_active, case_open)

    ExpenseFactory(
        case=case_open,
        client=c_active,
        amount=Decimal("50.00"),
        currency="ILS",
        category=ExpenseCategory.COURT_FEES,
    )
    ExpenseFactory(
        case=case_open,
        client=c_active,
        amount=Decimal("20.00"),
        currency="USD",
        category=ExpenseCategory.TRAVEL,
    )

    return {
        "actor": actor,
        "court": court,
        "type": ctype,
        "client_active": c_active,
        "client_prospect": c_prospect,
        "case_open": case_open,
        "case_closed": case_closed,
        "inv_ils": inv_ils,
        "inv_usd": inv_usd,
    }


def _issue_usd(actor, client, case):
    inv = services.create_invoice(
        actor=actor,
        data={
            "client": client,
            "case": case,
            "due_date": dt.date.today() - dt.timedelta(days=10),
            "currency": "USD",
            "tax_rate": Decimal("0"),
        },
    )
    services.add_line_item(
        actor=actor,
        invoice=inv,
        data={"description": "consult", "quantity": Decimal("1"), "unit_price": Decimal("500.00")},
    )
    inv = services.issue_invoice(actor=actor, invoice=inv)
    inv.issue_date = dt.date.today() - dt.timedelta(days=40)
    inv.save(update_fields=["issue_date"])
    return inv


def _date(days: int) -> dt.date:
    return dt.date.today() + dt.timedelta(days=days)


def _days(days: int):
    from django.utils import timezone

    return timezone.now() + dt.timedelta(days=days)
