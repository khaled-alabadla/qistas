import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from agenda.selectors import calendar_events
from agenda.views import _week_start
from hearings.models import HearingStatus
from hearings.tests.factories import HearingFactory

pytestmark = pytest.mark.django_db


def test_week_start_is_saturday():
    # 2026-09-09 is a Wednesday
    assert _week_start(dt.date(2026, 9, 9)) == dt.date(2026, 9, 5)  # Saturday
    assert _week_start(dt.date(2026, 9, 5)).weekday() == 5


def test_calendar_events_from_hearings(user):
    when = timezone.now() + dt.timedelta(days=1)
    h = HearingFactory(scheduled_at=when)
    events = calendar_events(user, when - dt.timedelta(days=2), when + dt.timedelta(days=2))
    assert len(events) == 1
    assert events[0]["kind"] == "hearing"
    assert events[0]["url"] == reverse("hearings:detail", args=[h.pk])


def test_calendar_events_excludes_cancelled(user):
    when = timezone.now() + dt.timedelta(days=1)
    HearingFactory(scheduled_at=when, status=HearingStatus.CANCELLED)
    events = calendar_events(user, when - dt.timedelta(days=2), when + dt.timedelta(days=2))
    assert events == []


def test_calendar_events_scoped_to_authed(client):
    HearingFactory(scheduled_at=timezone.now() + dt.timedelta(days=1))
    assert calendar_events(None, timezone.now(), timezone.now() + dt.timedelta(days=5)) == []


@pytest.mark.parametrize("view", ["agenda:month", "agenda:week", "agenda:day"])
def test_agenda_views_render_for_staff(client, finance_clerk, view):
    HearingFactory(scheduled_at=timezone.now() + dt.timedelta(days=1))
    client.force_login(finance_clerk)
    resp = client.get(reverse(view))
    assert resp.status_code == 200
    assert resp.context["view"] == view.split(":")[1]


def test_agenda_requires_login(client):
    resp = client.get(reverse("agenda:month"))
    assert resp.status_code == 302


def test_month_view_accepts_year_month(client, office_manager):
    client.force_login(office_manager)
    resp = client.get(reverse("agenda:month"), {"year": "2026", "month": "1"})
    assert resp.status_code == 200
    assert "كانون الثاني" in resp.context["heading"]


def test_month_view_ignores_bad_params(client, office_manager):
    client.force_login(office_manager)
    resp = client.get(reverse("agenda:month"), {"year": "abc", "month": "99"})
    assert resp.status_code == 200
