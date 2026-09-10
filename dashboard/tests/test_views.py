"""HTTP smoke for the Phase 9 dashboard (= ``core:landing``)."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from cases.models import CasePriority, CaseStatus
from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from contracts.models import ContractStatus
from contracts.tests.factories import ContractFactory
from finance.tests.factories import ExpenseFactory, issued_invoice
from hearings.tests.factories import HearingFactory
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


def _full_office(office_manager):
    today_9 = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
    c = CaseFactory(status=CaseStatus.IN_PROGRESS, priority=CasePriority.URGENT)
    HearingFactory(case=c, scheduled_at=today_9)
    TaskFactory(case=c, due_date=dt.date.today() - dt.timedelta(days=1))
    DeadlineFactory(case=c, due_date=dt.date.today() - dt.timedelta(days=1))
    ContractFactory(
        client=c.client,
        status=ContractStatus.ACTIVE,
        end_date=dt.date.today() + dt.timedelta(days=10),
    )
    inv = issued_invoice(actor=office_manager, client=c.client, lines=[("x", 1, "1000")])
    inv.due_date = dt.date.today() - dt.timedelta(days=2)
    inv.save(update_fields=["due_date"])
    ExpenseFactory(case=c, client=c.client, amount=Decimal("40"))
    ClientFactory.create_batch(2)


def test_dashboard_renders_full(client, office_manager):
    _full_office(office_manager)
    client.force_login(office_manager)
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 200
    body = resp.content.decode()
    for text in (
        "ما الذي يحتاج إلى انتباهك اليوم؟",
        "جلسات اليوم",
        "يحتاج إلى انتباه",
        "تحليلات القضايا",
        "الملخص المالي",
        "مواعيد نهائية قادمة",
        "النشاط الأخير",
    ):
        assert text in body, text


def test_dashboard_renders_for_every_role(client, role_user):
    for role in ("office_manager", "finance_clerk", "lawyer", "paralegal", "admin_clerk"):
        client.force_login(role_user(role))
        assert client.get(reverse("core:landing")).status_code == 200


def test_dashboard_empty_office(client, office_manager):
    client.force_login(office_manager)
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "لا جلسات مجدولة اليوم." in body
    assert "كل شيء تحت السيطرة." in body


def test_dashboard_kpi_links_resolve(client, office_manager):
    _full_office(office_manager)
    client.force_login(office_manager)
    resp = client.get(reverse("core:landing"))
    for k in resp.context["kpis"]:
        assert k["url"] and k["url"].startswith("/")
