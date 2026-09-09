from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from cases.tests.factories import CaseFactory
from hearings.models import Hearing, HearingStatus
from hearings.tests.factories import HearingFactory

pytestmark = pytest.mark.django_db


def test_list_requires_login(client):
    resp = client.get(reverse("hearings:list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_list_renders_for_any_staff(client, finance_clerk):
    HearingFactory.create_batch(2)
    client.force_login(finance_clerk)
    resp = client.get(reverse("hearings:list"))
    assert resp.status_code == 200
    assert resp.context["total_count"] == 2


def test_list_upcoming_default_hides_past(client, office_manager):
    HearingFactory(scheduled_at=timezone.now() + timedelta(days=3))
    HearingFactory(scheduled_at=timezone.now() - timedelta(days=3))
    client.force_login(office_manager)
    assert client.get(reverse("hearings:list")).context["total_count"] == 1
    resp = client.get(reverse("hearings:list"), {"when": "all"})
    assert resp.context["total_count"] == 2


def test_list_paginates(client, office_manager):
    HearingFactory.create_batch(30, scheduled_at=timezone.now() + timedelta(days=5))
    client.force_login(office_manager)
    resp = client.get(reverse("hearings:list"))
    assert len(resp.context["hearings"]) == 25
    assert resp.context["page_obj"].paginator.num_pages == 2
    # page 2 keeps the same (default upcoming) filter — no leak of past/closed rows
    resp2 = client.get(reverse("hearings:list"), {"page": "2"})
    assert resp2.context["total_count"] == 30
    assert len(resp2.context["hearings"]) == 5


def test_list_search_by_case_number(client, office_manager):
    h = HearingFactory(scheduled_at=timezone.now() + timedelta(days=2))
    HearingFactory(scheduled_at=timezone.now() + timedelta(days=2))
    client.force_login(office_manager)
    resp = client.get(reverse("hearings:list"), {"q": h.case.case_number, "when": "all"})
    assert resp.context["total_count"] == 1


def test_detail_ok_and_missing_is_404(client, office_manager):
    h = HearingFactory()
    client.force_login(office_manager)
    assert client.get(reverse("hearings:detail", args=[h.pk])).status_code == 200
    assert client.get(reverse("hearings:detail", args=[999999])).status_code == 404


def test_schedule_from_case_prefills_and_creates(client, office_manager):
    case = CaseFactory()
    client.force_login(office_manager)
    resp = client.post(
        reverse("hearings:schedule") + f"?case={case.pk}",
        {
            "case": case.pk,
            "date": (date.today() + timedelta(days=10)).isoformat(),
            "hearing_type": "pleading",
        },
    )
    assert resp.status_code == 302
    h = Hearing.objects.get(case=case)
    assert h.hearing_type == "pleading"
    assert h.created_by == office_manager


def test_schedule_forbidden_for_finance_clerk(client, finance_clerk):
    case = CaseFactory()
    client.force_login(finance_clerk)
    resp = client.post(
        reverse("hearings:schedule"),
        {
            "case": case.pk,
            "date": (date.today() + timedelta(days=5)).isoformat(),
            "hearing_type": "other",
        },
    )
    assert resp.status_code == 403
    assert not Hearing.objects.exists()


def test_complete_action_flow(client, office_manager):
    h = HearingFactory()
    client.force_login(office_manager)
    resp = client.post(
        reverse("hearings:complete", args=[h.pk]),
        {"result": "حكم", "next_hearing_date": (date.today() + timedelta(days=15)).isoformat()},
    )
    assert resp.status_code == 302
    h.refresh_from_db()
    assert h.status == HearingStatus.HELD
    assert Hearing.objects.filter(case=h.case).count() == 2


def test_cancel_requires_post(client, office_manager):
    h = HearingFactory()
    client.force_login(office_manager)
    assert client.get(reverse("hearings:cancel", args=[h.pk])).status_code == 405


def test_cancel_with_reason_via_view(client, office_manager):
    h = HearingFactory()
    client.force_login(office_manager)
    resp = client.post(reverse("hearings:cancel", args=[h.pk]), {"reason": "تسوية ودية"})
    assert resp.status_code == 302
    h.refresh_from_db()
    assert h.status == HearingStatus.CANCELLED
    assert h.notes == "تسوية ودية"


def test_action_on_closed_hearing_redirects_with_message(client, office_manager):
    h = HearingFactory(status=HearingStatus.HELD)
    client.force_login(office_manager)
    resp = client.get(reverse("hearings:complete", args=[h.pk]))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("hearings:detail", args=[h.pk])


def test_edit_hearing_keeps_deactivated_court(client, office_manager):
    from courts.tests.factories import CourtFactory

    court = CourtFactory(name="محكمة معطلة", city="غزة")
    h = HearingFactory(court=court)
    court.is_active = False
    court.save()
    client.force_login(office_manager)
    form = client.get(reverse("hearings:update", args=[h.pk])).context["form"]
    assert court in list(form.fields["court"].queryset)
