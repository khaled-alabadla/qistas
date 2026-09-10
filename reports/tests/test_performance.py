"""Query-count regression for the report builders (spec Phase 10 §14).

A builder must issue a **bounded** number of queries — flat regardless of how
many rows match (no N+1 in the row loop)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cases.models import CasePriority, CaseStatus
from cases.tests.factories import CaseFactory
from finance.tests.factories import ExpenseFactory, issued_invoice
from hearings.tests.factories import HearingFactory
from reports.selectors import (
    build_case_report,
    build_expense_report,
    build_hearing_report,
    build_revenue_report,
    build_task_report,
)
from tasks.tests.factories import TaskFactory

pytestmark = pytest.mark.django_db

_WIDE = {
    "date_from": dt.date.today() - dt.timedelta(days=3650),
    "date_to": dt.date.today() + dt.timedelta(days=3650),
}


def _seed(actor, n):
    for _ in range(n):
        c = CaseFactory(
            assigned_lawyer=actor, status=CaseStatus.IN_PROGRESS, priority=CasePriority.URGENT
        )
        HearingFactory(case=c)
        TaskFactory(case=c, assigned_to=actor, due_date=dt.date.today())
        inv = issued_invoice(actor=actor, client=c.client, case=c, lines=[("x", 1, "100.00")])
        inv.issue_date = dt.date.today()
        inv.save(update_fields=["issue_date"])
        ExpenseFactory(case=c, client=c.client, amount=Decimal("10.00"))


@pytest.mark.parametrize(
    "builder,filters",
    [
        (build_case_report, {"open_only": True}),
        (build_hearing_report, _WIDE),
        (build_task_report, {}),
        (build_revenue_report, _WIDE),
        (build_expense_report, _WIDE),
    ],
)
def test_builder_query_count_is_flat(office_manager, builder, filters):
    _seed(office_manager, 2)
    with CaptureQueriesContext(connection) as small:
        builder(user=office_manager, filters=dict(filters))
    _seed(office_manager, 8)  # 5x the rows
    with CaptureQueriesContext(connection) as big:
        builder(user=office_manager, filters=dict(filters))

    assert len(big.captured_queries) == len(small.captured_queries), (
        f"{builder.__name__}: {len(small.captured_queries)} → {len(big.captured_queries)} "
        f"— a query scales with the number of rows (N+1)"
    )
    assert len(small.captured_queries) <= 15


def test_report_page_is_bounded(client, office_manager):
    _seed(office_manager, 3)
    client.force_login(office_manager)
    from django.urls import reverse

    with CaptureQueriesContext(connection) as small:
        client.get(reverse("reports:detail", args=["revenue"]))
    _seed(office_manager, 10)
    with CaptureQueriesContext(connection) as big:
        client.get(reverse("reports:detail", args=["revenue"]))
    assert len(big.captured_queries) <= len(small.captured_queries) + 1
