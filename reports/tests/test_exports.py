"""CSV export — content, formula-injection guard, filename, audit, and the
authorization-before-generation rule (spec Phase 10 §11, §12, §17, §18)."""

from __future__ import annotations

import csv
import datetime as dt
import io

import pytest
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.tests.factories import CaseFactory
from reports.framework import csv_safe

pytestmark = pytest.mark.django_db


def _read_csv(resp):
    text = resp.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def _csv(client, slug, **params):
    # a real "export" link carries the filter-submission marker (_run) plus
    # whatever filters were applied; bare params here stand in for that.
    payload = {"format": "csv"}
    if params:
        payload["_run"] = "1"
    payload.update(params)
    return client.get(reverse("reports:detail", args=[slug]), payload)


# ── content ──────────────────────────────────────────────────────────────
def test_cases_csv_headers_and_rows(client, office):
    client.force_login(office["actor"])
    resp = _csv(client, "cases", open_only="on")
    assert resp["Content-Type"].startswith("text/csv")
    rows = _read_csv(resp)
    assert rows[0] == [
        "رقم القضية",
        "العنوان",
        "الموكل",
        "النوع",
        "الحالة",
        "الأولوية",
        "المحامي",
        "المحكمة",
        "تاريخ الفتح",
    ]
    body = {r[0] for r in rows[1:]}
    assert office["case_open"].case_number in body
    assert office["case_closed"].case_number not in body


def test_money_cells_are_plain_decimal_strings(client, office):
    client.force_login(office["actor"])
    rows = _read_csv(_csv(client, "revenue", date_from="2000-01-01", date_to="2100-01-01"))
    header = rows[0]
    total_idx = header.index("الإجمالي")
    values = [r[total_idx] for r in rows[1:]]
    assert "1000.00" in values and "500.00" in values
    for v in values:
        assert v.replace(".", "").isdigit()  # no grouping, no currency glued on


def test_csv_has_utf8_bom(client, office):
    client.force_login(office["actor"])
    resp = _csv(client, "cases")
    assert resp.content.startswith(b"\xef\xbb\xbf")


def test_csv_content_disposition_filename_is_server_generated(client, office):
    client.force_login(office["actor"])
    resp = _csv(client, "revenue")
    today = dt.date.today().isoformat()
    assert resp["Content-Disposition"] == f'attachment; filename="qistas-revenue-{today}.csv"'


# ── formula injection (spec Phase 10 §12) ────────────────────────────────
def test_formula_injection_is_neutralised_in_export(client, office):
    CaseFactory(title="=SUM(A1:A9)+cmd", status="new", client=office["client_active"])
    client.force_login(office["actor"])
    rows = _read_csv(_csv(client, "cases", open_only="on"))
    titles = [r[1] for r in rows[1:]]
    assert "=SUM(A1:A9)+cmd" not in titles
    assert "'=SUM(A1:A9)+cmd" in titles


@pytest.mark.parametrize("dangerous", ["=1+1", "+1", "-1", "@x", "\tval"])
def test_csv_safe_prefixes_dangerous_leading_chars(dangerous):
    out = csv_safe(dangerous)
    assert out.startswith("'")


@pytest.mark.parametrize("safe", ["hello", "قضية", "12ab", "ILS 100"])
def test_csv_safe_leaves_ordinary_text_untouched(safe):
    assert csv_safe(safe) == safe


# ── authorization is checked BEFORE the file is generated ────────────────
def test_paralegal_export_of_financial_report_is_403_no_file(client, paralegal):
    client.force_login(paralegal)
    resp = _csv(client, "revenue")
    assert resp.status_code == 403
    assert "text/csv" not in resp.get("Content-Type", "")


def test_anonymous_export_redirects_to_login(client):
    resp = _csv(client, "cases")
    assert resp.status_code == 302 and "/accounts/login/" in resp["Location"]


# ── audit (spec Phase 10 §17) ───────────────────────────────────────────
def test_financial_export_is_audited_metadata_only(client, office):
    client.force_login(office["actor"])
    _csv(client, "revenue", currency="USD")
    log = AuditLog.objects.filter(action=AuditAction.REPORT_EXPORTED).latest("created_at")
    assert log.entity_type == "reports.report"
    assert log.entity_id == "revenue"
    assert log.changes["report"] == "revenue"
    assert log.changes["format"] == "csv"
    assert log.changes["financial"] is True
    assert log.changes["filters"]["currency"] == "USD"
    # no row content, no money figures leaked into the metadata
    blob = str(log.changes)
    assert "1000.00" not in blob and "500.00" not in blob


def test_general_export_is_also_audited(client, office):
    client.force_login(office["actor"])
    _csv(client, "cases")
    assert AuditLog.objects.filter(action=AuditAction.REPORT_EXPORTED, entity_id="cases").exists()


def test_viewing_the_html_page_is_not_audited(client, office):
    client.force_login(office["actor"])
    client.get(reverse("reports:detail", args=["revenue"]))
    assert not AuditLog.objects.filter(action=AuditAction.REPORT_EXPORTED).exists()
