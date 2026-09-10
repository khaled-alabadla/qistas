import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from audit.models import AuditAction
from cases.models import CasePriority, CaseStatus
from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from contracts.models import ContractStatus
from contracts.tests.factories import ContractFactory
from dashboard.selectors import build_dashboard
from finance.tests.factories import ExpenseFactory, issued_invoice
from hearings.models import HearingStatus, HearingType
from hearings.tests.factories import HearingFactory
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


def _kpi(ctx, key):
    return next((k for k in ctx["kpis"] if k["key"] == key), None)


def _block(ctx, key):
    return next((b for b in ctx["attention"]["blocks"] if b["key"] == key), None)


# ── KPIs (spec §18) ────────────────────────────────────────
def test_active_case_kpi_counts_open_only(office_manager):
    CaseFactory.create_batch(3, status=CaseStatus.IN_PROGRESS)
    CaseFactory(status=CaseStatus.CLOSED)
    CaseFactory(status=CaseStatus.CONCLUDED)
    ctx = build_dashboard(office_manager)
    assert _kpi(ctx, "active_cases")["value"] == 3


def test_urgent_case_kpi(office_manager):
    CaseFactory(status=CaseStatus.NEW, priority=CasePriority.URGENT)
    CaseFactory(status=CaseStatus.NEW, priority=CasePriority.LOW)
    CaseFactory(status=CaseStatus.CLOSED, priority=CasePriority.URGENT)  # closed → not counted
    ctx = build_dashboard(office_manager)
    assert _kpi(ctx, "urgent_cases")["value"] == 1
    assert _kpi(ctx, "urgent_cases")["tone"] == "warning"


def test_today_hearings_kpi_and_rows(office_manager):
    today_9 = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
    HearingFactory(scheduled_at=today_9, hearing_type=HearingType.FIRST_SESSION)
    HearingFactory(scheduled_at=today_9 + dt.timedelta(days=1))  # tomorrow
    HearingFactory(scheduled_at=today_9, status=HearingStatus.CANCELLED)  # not scheduled
    ctx = build_dashboard(office_manager)
    assert _kpi(ctx, "today_hearings")["value"] == 1
    assert len(ctx["today_hearings"]) == 1
    row = ctx["today_hearings"][0]
    assert {"at", "case_number", "client", "court", "lawyer", "status", "url"} <= set(row)


def test_overdue_task_kpi_is_computed_not_stored(office_manager):
    TaskFactory(due_date=dt.date.today() - dt.timedelta(days=2))
    TaskFactory(due_date=dt.date.today() - dt.timedelta(days=2), status="done")  # closed
    TaskFactory(due_date=dt.date.today() + dt.timedelta(days=2))  # future
    ctx = build_dashboard(office_manager)
    assert _kpi(ctx, "overdue_tasks")["value"] == 1
    assert _kpi(ctx, "overdue_tasks")["tone"] == "danger"


def test_expiring_contracts_kpi(office_manager):
    ContractFactory(status=ContractStatus.ACTIVE, end_date=dt.date.today() + dt.timedelta(days=10))
    ContractFactory(status=ContractStatus.ACTIVE, end_date=dt.date.today() + dt.timedelta(days=300))
    ctx = build_dashboard(office_manager)
    assert _kpi(ctx, "expiring_contracts")["value"] == 1


# ── Attention (spec §19) ───────────────────────────────────
def test_attention_overdue_deadlines(office_manager):
    DeadlineFactory(due_date=dt.date.today() - dt.timedelta(days=1))
    DeadlineFactory(due_date=dt.date.today() + dt.timedelta(days=5))
    ctx = build_dashboard(office_manager)
    b = _block(ctx, "overdue_deadlines")
    assert b and b["count"] == 1 and b["tone"] == "danger"


def test_attention_upcoming_hearings_next_7_days(office_manager):
    HearingFactory(scheduled_at=timezone.now() + dt.timedelta(days=3))
    HearingFactory(scheduled_at=timezone.now() + dt.timedelta(days=20))
    ctx = build_dashboard(office_manager)
    b = _block(ctx, "upcoming_hearings")
    assert b and b["count"] == 1


def test_attention_empty_state(office_manager):
    ctx = build_dashboard(office_manager)
    assert ctx["attention"]["empty"] is True
    assert ctx["attention"]["blocks"] == []


# ── Case analytics (spec §19) ──────────────────────────────
def test_case_analytics_breakdowns(office_manager):
    CaseFactory(status=CaseStatus.NEW, priority=CasePriority.HIGH)
    CaseFactory(status=CaseStatus.NEW, priority=CasePriority.LOW)
    CaseFactory(status=CaseStatus.CLOSED, priority=CasePriority.LOW)
    ctx = build_dashboard(office_manager)
    a = ctx["case_analytics"]
    assert a["total"] == 3
    assert a["open_total"] == 2
    status_map = {r["key"]: r["value"] for r in a["by_status"]}
    assert status_map["new"] == 2 and status_map["closed"] == 1
    prio_map = {r["key"]: r["value"] for r in a["by_priority"]}  # open only
    assert prio_map.get("high") == 1 and prio_map.get("low") == 1


def test_case_analytics_by_lawyer_labels_unassigned(office_manager):
    CaseFactory(status=CaseStatus.NEW, assigned_lawyer=None)
    ctx = build_dashboard(office_manager)
    labels = [r["label"] for r in ctx["case_analytics"]["by_lawyer"]]
    assert "غير مُسندة" in labels


# ── Recent activity (spec §19) ─────────────────────────────
def test_recent_activity_shapes_and_filters_by_allowlist(office_manager):
    from audit.models import AuditLog

    c = CaseFactory()
    AuditLog.objects.create(
        actor=office_manager,
        action=AuditAction.CASE_CREATED,
        entity_type="cases.case",
        entity_id=str(c.pk),
        object_repr=str(c),
    )
    AuditLog.objects.create(actor=office_manager, action=AuditAction.LOGIN)  # not in allowlist
    AuditLog.objects.create(
        actor=office_manager, action=AuditAction.DOCUMENT_DOWNLOADED
    )  # not in allowlist

    ctx = build_dashboard(office_manager)
    rows = ctx["recent_activity"]
    assert len(rows) == 1
    assert rows[0]["label"] == AuditAction.CASE_CREATED.label
    assert rows[0]["url"].endswith(f"/cases/{c.pk}/")
    assert rows[0]["actor"] == office_manager.get_full_name() or office_manager.email


# ── Financial overview (spec §19) ──────────────────────────
def test_financial_overview_per_currency_and_credit_aware(office_manager):
    from finance import services

    cl = ClientFactory()
    ils = issued_invoice(actor=office_manager, client=cl, lines=[("x", 1, "1000")])
    services.issue_credit_note(
        actor=office_manager, invoice_id=ils.pk, data={"amount": Decimal("200"), "reason": "x"}
    )
    services.record_payment(
        actor=office_manager,
        invoice_id=ils.pk,
        data={"amount": Decimal("300"), "paid_on": None, "method": "cash"},
    )
    usd = issued_invoice(actor=office_manager, client=cl)  # default 5000 ILS... override:
    usd.currency = "USD"
    usd.save(update_fields=["currency"])
    ExpenseFactory(currency="ILS", amount=Decimal("50"))

    fin = build_dashboard(office_manager)["financial_overview"]
    assert fin["visible"] is True
    rows = {r["currency"]: r for r in fin["by_currency"]}
    assert rows["ILS"]["credited"] == Decimal("200.00")
    assert rows["ILS"]["outstanding"] == Decimal("500.00")  # 1000 - 200 - 300
    assert "USD" in rows
    assert fin["multi_currency"] is True
    exp = {e["currency"]: e["total"] for e in fin["expenses_by_currency"]}
    assert exp["ILS"] == Decimal("50.00")


def test_dashboard_owns_no_models():
    """Phase 9 is a read/analytics layer — it must not introduce domain models."""
    from django.apps import apps

    assert list(apps.get_app_config("dashboard").get_models()) == []
