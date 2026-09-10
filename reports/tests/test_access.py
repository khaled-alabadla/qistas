"""Authorization for the Reports layer (spec Phase 10 §6, §16, §18)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from reports.tests.conftest import ALL_REPORT_SLUGS, FINANCIAL_SLUGS, GENERAL_SLUGS

pytestmark = pytest.mark.django_db


def _url(slug):
    return reverse("reports:detail", args=[slug])


# ── anonymous ────────────────────────────────────────────────────────────
def test_index_requires_login(client):
    resp = client.get(reverse("reports:index"))
    assert resp.status_code == 302 and "/accounts/login/" in resp["Location"]


@pytest.mark.parametrize("slug", ALL_REPORT_SLUGS)
def test_every_report_requires_login(client, slug):
    resp = client.get(_url(slug))
    assert resp.status_code == 302 and "/accounts/login/" in resp["Location"]


def test_csv_export_requires_login(client):
    resp = client.get(_url("cases"), {"format": "csv"})
    assert resp.status_code == 302 and "/accounts/login/" in resp["Location"]


# ── unknown slug ─────────────────────────────────────────────────────────
def test_unknown_report_is_404(client, office_manager):
    client.force_login(office_manager)
    assert client.get(reverse("reports:detail", args=["totally-made-up"])).status_code == 404


# ── capability gating per report ─────────────────────────────────────────
@pytest.mark.parametrize("slug", GENERAL_SLUGS)
def test_paralegal_sees_general_reports(client, paralegal, slug):
    client.force_login(paralegal)
    assert client.get(_url(slug)).status_code == 200


@pytest.mark.parametrize("slug", FINANCIAL_SLUGS)
def test_paralegal_blocked_from_financial_reports(client, paralegal, slug):
    """The critical regression (spec Phase 10 §6): a paralegal has no
    finance.view, so every financial report — page AND export — is 403."""
    client.force_login(paralegal)
    assert client.get(_url(slug)).status_code == 403
    assert client.get(_url(slug), {"format": "csv"}).status_code == 403


@pytest.mark.parametrize("slug", FINANCIAL_SLUGS)
def test_finance_clerk_reaches_financial_reports(client, finance_clerk, slug):
    client.force_login(finance_clerk)
    assert client.get(_url(slug)).status_code == 200


# ── the index only lists what you can run ────────────────────────────────
def test_index_hides_financial_reports_from_paralegal(client, paralegal):
    client.force_login(paralegal)
    resp = client.get(reverse("reports:index"))
    body = resp.content.decode()
    assert "تقرير القضايا" in body
    assert "تقرير الإيرادات" not in body
    assert "الأداء المالي للقضايا" not in body


def test_index_lists_financial_reports_for_office_manager(client, office_manager):
    client.force_login(office_manager)
    body = client.get(reverse("reports:index")).content.decode()
    assert "تقرير الإيرادات" in body
    assert "الأداء المالي للقضايا" in body


def test_groupless_user_gets_a_safe_empty_index(client, user):
    client.force_login(user)
    resp = client.get(reverse("reports:index"))
    assert resp.status_code == 200
    assert "لا تتوفّر لك تقارير" in resp.content.decode()


def test_groupless_user_cannot_open_any_report(client, user):
    client.force_login(user)
    for slug in ALL_REPORT_SLUGS:
        assert client.get(_url(slug)).status_code == 403


# ── tampering ────────────────────────────────────────────────────────────
def test_format_param_other_than_csv_renders_html(client, office_manager):
    client.force_login(office_manager)
    resp = client.get(_url("cases"), {"format": "pdf"})
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")


def test_page_param_out_of_range_is_clamped(client, office_manager):
    client.force_login(office_manager)
    assert client.get(_url("cases"), {"page": "9999"}).status_code == 200
    assert client.get(_url("cases"), {"page": "not-a-number"}).status_code == 200
