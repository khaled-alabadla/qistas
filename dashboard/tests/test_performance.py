"""Dashboard query-count guards (spec Phase 9 §10 — 'a small number of
intentional queries', flat regardless of data volume)."""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cases.models import CasePriority, CaseStatus
from cases.tests.factories import CaseFactory
from contracts.models import ContractStatus
from contracts.tests.factories import ContractFactory
from dashboard.selectors import build_dashboard
from finance.tests.factories import ExpenseFactory, issued_invoice
from hearings.tests.factories import HearingFactory
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


def _populate(office_manager, n):
    today_9 = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
    for _ in range(n):
        c = CaseFactory(status=CaseStatus.IN_PROGRESS, priority=CasePriority.URGENT)
        HearingFactory(case=c, scheduled_at=today_9)
        HearingFactory(case=c, scheduled_at=timezone.now() + dt.timedelta(days=3))
        TaskFactory(case=c, due_date=dt.date.today() - dt.timedelta(days=1))
        DeadlineFactory(case=c, due_date=dt.date.today() - dt.timedelta(days=1))
        ContractFactory(
            client=c.client,
            status=ContractStatus.ACTIVE,
            end_date=dt.date.today() + dt.timedelta(days=10),
        )
        inv = issued_invoice(actor=office_manager, client=c.client, lines=[("x", 1, "100")])
        inv.due_date = dt.date.today() - dt.timedelta(days=2)
        inv.save(update_fields=["due_date"])
        ExpenseFactory(case=c, client=c.client, amount=Decimal("10"))


def test_build_dashboard_query_count_is_flat(office_manager):
    # Every list block is already "overflowing" (>_LIST_LIMIT) in both runs, so
    # the count is identical — it must not grow with the *number* of rows.
    _populate(office_manager, 8)
    with CaptureQueriesContext(connection) as small:
        build_dashboard(office_manager)
    _populate(office_manager, 24)  # 4x the rows, still one page per widget
    with CaptureQueriesContext(connection) as large:
        build_dashboard(office_manager)
    assert len(large.captured_queries) == len(small.captured_queries), (
        f"{len(small.captured_queries)} → {len(large.captured_queries)}: a query scales with rows"
    )
    # sanity ceiling — a small number of intentional queries, not an ORM sprawl
    assert len(small.captured_queries) <= 45


def test_dashboard_page_query_count_is_flat(client, office_manager):
    client.force_login(office_manager)
    _populate(office_manager, 8)
    with CaptureQueriesContext(connection) as small:
        client.get(reverse("core:landing"))
    _populate(office_manager, 24)
    with CaptureQueriesContext(connection) as large:
        client.get(reverse("core:landing"))
    assert len(large.captured_queries) <= len(small.captured_queries) + 1


def test_empty_dashboard_is_cheap(office_manager):
    with CaptureQueriesContext(connection) as ctx:
        build_dashboard(office_manager)
    assert len(ctx.captured_queries) <= 30  # no data → fewer overflow counts
