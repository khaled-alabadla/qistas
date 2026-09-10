"""Correctness of the non-financial reports (spec Phase 10 §18)."""

from __future__ import annotations

import datetime as dt

import pytest

from cases.models import CaseStatus
from cases.tests.factories import CaseFactory
from clients.models import ClientStatus
from clients.tests.factories import ClientFactory
from hearings.models import HearingStatus
from hearings.tests.factories import HearingFactory
from reports.selectors import (
    build_case_report,
    build_client_report,
    build_deadline_report,
    build_hearing_report,
    build_task_report,
)
from tasks.models import DeadlineStatus, TaskStatus
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


def _labels(result):
    return [c.label for c in result.columns]


def _col(result, label):
    return _labels(result).index(label)


# ── cases ────────────────────────────────────────────────────────────────
def test_case_report_open_only_excludes_terminal(office):
    r = build_case_report(user=office["actor"], filters={"open_only": True})
    numbers = {row[0].value for row in r.rows}
    assert office["case_open"].case_number in numbers
    assert office["case_closed"].case_number not in numbers


def test_case_report_status_filter_overrides_open_only(office):
    r = build_case_report(
        user=office["actor"], filters={"status": CaseStatus.CLOSED, "open_only": True}
    )
    numbers = {row[0].value for row in r.rows}
    assert numbers == {office["case_closed"].case_number}


def test_case_report_lawyer_and_court_filter(office):
    r = build_case_report(
        user=office["actor"],
        filters={"lawyer": office["actor"], "court": office["court"], "open_only": True},
    )
    assert [row[0].value for row in r.rows] == [office["case_open"].case_number]


def test_case_report_metrics_count_by_status(office):
    r = build_case_report(user=office["actor"], filters={"open_only": False})
    total = next(m.value for m in r.metrics if m.label == "إجمالي القضايا")
    assert total == len(r.rows) == 2


def test_status_breakdown_is_not_inflated_by_the_row_ordering(office):
    """`.order_by(created_at)` on the row queryset must not widen the GROUP BY
    of the by-status metric — several NEW cases with distinct timestamps still
    count as one 'NEW' bucket, not one row each."""
    import datetime as _dt

    for i in range(4):
        c = CaseFactory(status=CaseStatus.NEW)
        c.created_at = _dt.datetime(2025, 1, 1, 8, i, tzinfo=_dt.UTC)
        c.save(update_fields=["created_at"])
    r = build_case_report(user=office["actor"], filters={"status": CaseStatus.NEW})
    new_count = next(m.value for m in r.metrics if m.label == CaseStatus.NEW.label)
    assert new_count == len(r.rows) == 4


def test_case_report_date_window_uses_registration_date(office):
    old = CaseFactory(status=CaseStatus.NEW)
    old.created_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    old.save(update_fields=["created_at"])
    r = build_case_report(
        user=office["actor"],
        filters={"date_from": dt.date(2019, 1, 1), "date_to": dt.date(2020, 12, 31)},
    )
    assert [row[0].value for row in r.rows] == [old.case_number]


# ── clients ──────────────────────────────────────────────────────────────
def test_client_report_active_case_count(office):
    r = build_client_report(user=office["actor"], filters={})
    row = next(row for row in r.rows if row[0].value == office["client_active"].client_number)
    active_idx = _col(r, "قضايا نشطة")
    assert row[active_idx].value == 1  # one open, one closed


def test_client_report_with_active_cases_filter(office):
    r = build_client_report(user=office["actor"], filters={"with_active_cases": True})
    numbers = {row[0].value for row in r.rows}
    assert office["client_active"].client_number in numbers
    assert office["client_prospect"].client_number not in numbers


def test_client_report_status_metrics(office):
    ClientFactory(full_name="أرشيف", status=ClientStatus.ARCHIVED)
    r = build_client_report(user=office["actor"], filters={})
    m = {metric.label: metric.value for metric in r.metrics}
    assert m["مؤرشف"] == 1
    assert m["عميل محتمل"] == 1


# ── hearings ─────────────────────────────────────────────────────────────
def test_hearing_report_status_filter_and_ordering(office):
    r = build_hearing_report(
        user=office["actor"],
        filters={
            "date_from": dt.date.today() - dt.timedelta(days=365),
            "date_to": dt.date.today() + dt.timedelta(days=365),
        },
    )
    times = [row[0].value for row in r.rows]
    assert times == sorted(times)  # scheduled_at ascending


def test_hearing_report_counts_every_status(office):
    HearingFactory(case=office["case_open"], status=HearingStatus.CANCELLED)
    r = build_hearing_report(
        user=office["actor"],
        filters={
            "date_from": dt.date.today() - dt.timedelta(days=365),
            "date_to": dt.date.today() + dt.timedelta(days=365),
        },
    )
    m = {metric.label: metric.value for metric in r.metrics}
    assert m["ملغاة"] == 1
    assert m["مجدولة"] >= 1
    assert m["تمت"] >= 1


# ── tasks ────────────────────────────────────────────────────────────────
def test_task_report_overdue_only_is_computed(office):
    r = build_task_report(user=office["actor"], filters={"overdue_only": True})
    # the NEW task due 3 days ago is overdue; the DONE task is not
    assert len(r.rows) == 1
    overdue_col = r.columns.index(next(c for c in r.columns if c.label == "متأخرة؟"))
    assert r.rows[0][overdue_col].value == "نعم"


def test_task_report_status_filter(office):
    r = build_task_report(user=office["actor"], filters={"status": TaskStatus.DONE})
    assert len(r.rows) == 1


def test_task_report_by_employee_metric(office):
    r = build_task_report(user=office["actor"], filters={})
    assert any(m.label.startswith("للموظف:") for m in r.metrics)


def test_task_report_excludes_soft_deleted(office):
    t = TaskFactory(case=office["case_open"], status=TaskStatus.NEW, due_date=dt.date.today())
    t.deleted_at = dt.datetime.now(dt.UTC)
    t.save(update_fields=["deleted_at"])
    r = build_task_report(user=office["actor"], filters={})
    assert t.title not in {row[0].value for row in r.rows}


# ── deadlines ────────────────────────────────────────────────────────────
def test_deadline_report_overdue_only(office):
    r = build_deadline_report(user=office["actor"], filters={"overdue_only": True})
    assert len(r.rows) == 1  # the PENDING one due 2 days ago


def test_deadline_report_status_counts(office):
    r = build_deadline_report(user=office["actor"], filters={})
    m = {metric.label: metric.value for metric in r.metrics}
    assert m["معلق"] == 1
    assert m["مستوفى"] == 1


def test_deadline_report_missed_status_filter(office):
    DeadlineFactory(
        case=office["case_open"], status=DeadlineStatus.MISSED, due_date=dt.date.today()
    )
    r = build_deadline_report(user=office["actor"], filters={"status": DeadlineStatus.MISSED})
    assert len(r.rows) == 1
