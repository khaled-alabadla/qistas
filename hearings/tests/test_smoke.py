"""End-to-end HTTP smoke for the Phase 4 surface (courts + hearings + agenda)."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from cases.tests.factories import CaseFactory
from courts.tests.factories import CourtFactory
from hearings.tests.factories import HearingFactory

pytestmark = pytest.mark.django_db


def test_phase4_pages_render(client, office_manager):
    client.force_login(office_manager)
    court = CourtFactory(name="محكمة سموك", city="نابلس")
    case = CaseFactory()
    h = HearingFactory(case=case, court=court, scheduled_at=timezone.now() + dt.timedelta(days=2))
    urls = [
        reverse("courts:list"),
        reverse("courts:create"),
        reverse("courts:detail", args=[court.pk]),
        reverse("courts:update", args=[court.pk]),
        reverse("hearings:list"),
        reverse("hearings:schedule"),
        reverse("hearings:schedule") + f"?case={case.pk}",
        reverse("hearings:detail", args=[h.pk]),
        reverse("hearings:update", args=[h.pk]),
        reverse("hearings:complete", args=[h.pk]),
        reverse("hearings:postpone", args=[h.pk]),
        reverse("agenda:month"),
        reverse("agenda:week"),
        reverse("agenda:day"),
        reverse("cases:detail", args=[case.pk]) + "?tab=hearings",
        reverse("cases:list"),
    ]
    for url in urls:
        assert client.get(url).status_code == 200, url
