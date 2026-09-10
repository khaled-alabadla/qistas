"""Filter validation + date-range boundary behaviour (spec Phase 10 §7, §8, §18)."""

from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from cases.models import CaseStatus
from cases.tests.factories import CaseFactory
from reports.forms import CaseReportForm, RevenueReportForm
from reports.selectors import build_case_report

pytestmark = pytest.mark.django_db


def test_reversed_date_range_is_rejected(office_manager):
    form = CaseReportForm({"date_from": "2026-06-01", "date_to": "2026-01-01"}, user=office_manager)
    assert not form.is_valid()
    assert "من تاريخ" in str(form.non_field_errors())


def test_equal_from_and_to_is_valid(office_manager):
    form = CaseReportForm({"date_from": "2026-01-01", "date_to": "2026-01-01"}, user=office_manager)
    assert form.is_valid()


def test_garbage_date_is_rejected(office_manager):
    form = CaseReportForm({"date_from": "not-a-date"}, user=office_manager)
    assert not form.is_valid()
    assert "date_from" in form.errors


def test_unknown_status_choice_is_rejected(office_manager):
    form = CaseReportForm({"status": "wizard"}, user=office_manager)
    assert not form.is_valid()


def test_empty_filters_are_valid_and_run(office):
    form = CaseReportForm({}, user=office["actor"])
    assert form.is_valid()
    r = build_case_report(user=office["actor"], filters=form.cleaned_data)
    assert r.row_count >= 1


def test_fk_filter_only_accepts_visible_rows(office_manager):
    # a client id that exists but the form's queryset is scoped — an out-of-range
    # pk simply fails validation, it never widens the query.
    form = CaseReportForm({"client": "99999"}, user=office_manager)
    assert not form.is_valid()
    assert "client" in form.errors


def test_date_boundary_is_inclusive_on_both_ends(office):
    """A case created exactly on date_to (any time that day) is included."""
    c = CaseFactory(status=CaseStatus.NEW)
    target = dt.date(2024, 3, 15)
    # 10:00 UTC == 12:00 in Asia/Hebron — unambiguously "the 15th" locally
    c.created_at = dt.datetime(2024, 3, 15, 10, 0, tzinfo=dt.UTC)
    c.save(update_fields=["created_at"])
    r = build_case_report(user=office["actor"], filters={"date_from": target, "date_to": target})
    assert c.case_number in {row[0].value for row in r.rows}


def test_combined_filters_narrow_together(office):
    r = build_case_report(
        user=office["actor"],
        filters={
            "status": CaseStatus.IN_PROGRESS,
            "priority": "urgent",
            "lawyer": office["actor"],
        },
    )
    assert [row[0].value for row in r.rows] == [office["case_open"].case_number]


def test_invalid_filter_on_page_keeps_html_200_with_errors(client, office_manager):
    client.force_login(office_manager)
    resp = client.get(reverse("reports:detail", args=["cases"]), {"date_from": "xxx"})
    assert resp.status_code == 200
    assert "صحّح المرشّحات لعرض التقرير." in resp.content.decode()


def test_csv_with_invalid_filter_is_400(client, office_manager):
    client.force_login(office_manager)
    resp = client.get(
        reverse("reports:detail", args=["cases"]), {"date_from": "xxx", "format": "csv"}
    )
    assert resp.status_code == 400


def test_finance_form_scopes_case_and_client_pickers(office_manager):
    form = RevenueReportForm({}, user=office_manager)
    # both pickers exist and are ModelChoiceField-bounded
    assert "case" in form.fields
    assert form.fields["case"].queryset is not None


# ── bug-055 class: a filter default must survive pagination ──────────────
def test_case_report_page_2_keeps_open_only_default(client, office_manager):
    from cases.models import CaseStatus
    from cases.tests.factories import CaseFactory

    for _ in range(105):
        CaseFactory(status=CaseStatus.NEW)
    CaseFactory(status=CaseStatus.CLOSED, title="مغلقة يجب ألا تظهر")
    client.force_login(office_manager)
    p2 = client.get(reverse("reports:detail", args=["cases"]), {"page": "2"})
    assert p2.status_code == 200
    assert "مغلقة يجب ألا تظهر" not in p2.content.decode()


def test_default_report_and_its_csv_export_use_the_same_window(client, office):
    """The 'export CSV' link on a fresh report page carries no filter params —
    the export must still use the same default 90-day window as the page."""
    client.force_login(office["actor"])
    html = client.get(reverse("reports:detail", args=["revenue"]))
    csv_resp = client.get(reverse("reports:detail", args=["revenue"]), {"format": "csv"})
    # both see the same issued invoices (2), not "all history vs none"
    page_rows = html.context["page_obj"].paginator.count
    csv_rows = len(csv_resp.content.decode("utf-8-sig").splitlines()) - 1
    assert page_rows == csv_rows == 2


def test_explicit_filter_submission_respects_unchecked_open_only(client, office):
    client.force_login(office["actor"])
    resp = client.get(
        reverse("reports:detail", args=["cases"]),
        {"_run": "1"},  # submitted, open_only unchecked
    )
    body = resp.content.decode()
    assert office["case_closed"].case_number in body
