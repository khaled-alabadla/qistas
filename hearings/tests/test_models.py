from datetime import timedelta

import pytest
from django.utils import timezone

from cases.tests.factories import CaseFactory
from hearings.models import Hearing, HearingStatus
from hearings.tests.factories import HearingFactory

pytestmark = pytest.mark.django_db


def test_for_user_scopes_and_denies_anon():
    HearingFactory()
    assert Hearing.objects.for_user(None).count() == 0


def test_for_user_returns_all_for_authed(user):
    HearingFactory.create_batch(3)
    assert Hearing.objects.for_user(user).count() == 3


def test_upcoming_excludes_past_and_non_scheduled():
    future = HearingFactory(scheduled_at=timezone.now() + timedelta(days=2))
    HearingFactory(scheduled_at=timezone.now() - timedelta(days=2))
    HearingFactory(scheduled_at=timezone.now() + timedelta(days=3), status=HearingStatus.CANCELLED)
    upcoming = list(Hearing.objects.upcoming())
    assert upcoming == [future]


def test_case_next_hearing_is_derived_soonest_scheduled():
    case = CaseFactory()
    HearingFactory(case=case, scheduled_at=timezone.now() + timedelta(days=10))
    soon = HearingFactory(case=case, scheduled_at=timezone.now() + timedelta(days=2))
    HearingFactory(case=case, scheduled_at=timezone.now() - timedelta(days=1))
    assert case.next_hearing == soon


def test_case_next_hearing_none_when_only_closed_or_past():
    case = CaseFactory()
    HearingFactory(case=case, scheduled_at=timezone.now() - timedelta(days=1))
    HearingFactory(
        case=case,
        scheduled_at=timezone.now() + timedelta(days=5),
        status=HearingStatus.HELD,
    )
    assert case.next_hearing is None


def test_hearing_not_deletable_via_admin_permission():
    assert "delete_hearing" not in [p.split(".")[-1] for p in Hearing._meta.default_permissions]
