"""HTML rendering of the reports (spec Phase 10 §15)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from reports.tests.conftest import ALL_REPORT_SLUGS

pytestmark = pytest.mark.django_db


def test_index_renders(client, office_manager):
    client.force_login(office_manager)
    resp = client.get(reverse("reports:index"))
    assert resp.status_code == 200
    assert "التقارير" in resp.content.decode()


@pytest.mark.parametrize("slug", ALL_REPORT_SLUGS)
def test_every_report_page_renders_with_data(client, office, slug):
    client.force_login(office["actor"])
    resp = client.get(reverse("reports:detail", args=[slug]))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "تصدير CSV" in body
    assert "تطبيق" in body  # the filter form


@pytest.mark.parametrize("slug", ALL_REPORT_SLUGS)
def test_every_report_renders_for_an_empty_office(client, office_manager, slug):
    client.force_login(office_manager)
    resp = client.get(reverse("reports:detail", args=[slug]))
    assert resp.status_code == 200
    # no data → the empty state, never a crash
    assert "لا سجلّات مطابقة" in resp.content.decode() or "لا تتوفّر" in resp.content.decode()


def test_report_page_shows_per_currency_blocks_not_a_grand_total(client, office):
    client.force_login(office["actor"])
    body = client.get(reverse("reports:detail", args=["revenue"])).content.decode()
    assert "ILS" in body and "USD" in body


def test_nav_shows_reports_link(client, office_manager):
    client.force_login(office_manager)
    body = client.get(reverse("reports:index")).content.decode()
    assert reverse("reports:index") in body


def test_report_pagination(client, office_manager):
    from cases.models import CaseStatus
    from cases.tests.factories import CaseFactory

    for _ in range(105):
        CaseFactory(status=CaseStatus.NEW)
    client.force_login(office_manager)
    resp = client.get(reverse("reports:detail", args=["cases"]), {"open_only": "on"})
    assert resp.status_code == 200
    assert "التالي" in resp.content.decode()
    p2 = client.get(reverse("reports:detail", args=["cases"]), {"open_only": "on", "page": "2"})
    assert p2.status_code == 200
