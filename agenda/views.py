"""
Server-rendered month / week / day calendar (spec §33, docs/adr/0028).

Built on the stdlib ``calendar`` module — ``firstweekday = 5`` (Saturday, matching
the Palestinian working week). No JavaScript calendar library. Events come only
from ``agenda.selectors.calendar_events`` (scoped to the viewer).
"""

from __future__ import annotations

import calendar
import datetime as dt

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from agenda.selectors import calendar_events
from core.permissions.capabilities import Capability
from core.permissions.mixins import CapabilityRequiredMixin

SATURDAY = 5
_CAL = calendar.Calendar(firstweekday=SATURDAY)
WEEKDAY_NAMES = ["السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"]
MONTH_NAMES = [
    "",
    "كانون الثاني",
    "شباط",
    "آذار",
    "نيسان",
    "أيار",
    "حزيران",
    "تموز",
    "آب",
    "أيلول",
    "تشرين الأول",
    "تشرين الثاني",
    "كانون الأول",
]


def _aware(d: dt.date) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(d, dt.time.min), timezone.get_current_timezone())


def _parse_date(value: str | None) -> dt.date:
    if value:
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            pass
    return timezone.localdate()


def _week_start(d: dt.date) -> dt.date:
    """The Saturday on or before ``d``."""
    return d - dt.timedelta(days=(d.weekday() - SATURDAY) % 7)


def _bucket(events: list[dict]) -> dict[dt.date, list[dict]]:
    buckets: dict[dt.date, list[dict]] = {}
    for event in events:
        key = timezone.localtime(event["start"]).date()
        buckets.setdefault(key, []).append(event)
    return buckets


def _weekday_name(d: dt.date) -> str:
    return WEEKDAY_NAMES[(d.weekday() - SATURDAY) % 7]


class _AgendaBase(CapabilityRequiredMixin, LoginRequiredMixin, TemplateView):
    required_capability = Capability.AGENDA_VIEW

    def _events(self, start: dt.date, end: dt.date) -> dict[dt.date, list[dict]]:
        return _bucket(calendar_events(self.request.user, _aware(start), _aware(end)))


class AgendaMonthView(_AgendaBase):
    template_name = "agenda/month.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        try:
            year = int(self.request.GET.get("year", today.year))
            month = int(self.request.GET.get("month", today.month))
            dt.date(year, month, 1)
        except (ValueError, TypeError):
            year, month = today.year, today.month

        weeks = _CAL.monthdatescalendar(year, month)
        grid_start, grid_end = weeks[0][0], weeks[-1][-1] + dt.timedelta(days=1)
        buckets = self._events(grid_start, grid_end)

        prev_m = dt.date(year, month, 1) - dt.timedelta(days=1)
        next_m = weeks[-1][-1] + dt.timedelta(days=1)
        base = reverse("agenda:month")

        ctx.update(
            {
                "weeks": [
                    [
                        {
                            "date": d,
                            "in_month": d.month == month,
                            "is_today": d == today,
                            "events": buckets.get(d, []),
                        }
                        for d in week
                    ]
                    for week in weeks
                ],
                "weekday_names": WEEKDAY_NAMES,
                "heading": f"{MONTH_NAMES[month]} {year}",
                "prev_url": f"{base}?year={prev_m.year}&month={prev_m.month}",
                "next_url": f"{base}?year={next_m.year}&month={next_m.month}",
                "today_url": base,
                "view": "month",
            }
        )
        return ctx


class AgendaWeekView(_AgendaBase):
    template_name = "agenda/week.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        anchor = _parse_date(self.request.GET.get("date"))
        start = _week_start(anchor)
        days = [start + dt.timedelta(days=i) for i in range(7)]
        buckets = self._events(start, start + dt.timedelta(days=7))
        today = timezone.localdate()
        base = reverse("agenda:week")

        ctx.update(
            {
                "days": [
                    {
                        "date": d,
                        "weekday_name": WEEKDAY_NAMES[i],
                        "is_today": d == today,
                        "events": buckets.get(d, []),
                    }
                    for i, d in enumerate(days)
                ],
                "heading": f"{days[0].isoformat()} — {days[-1].isoformat()}",
                "prev_url": f"{base}?date={(start - dt.timedelta(days=7)).isoformat()}",
                "next_url": f"{base}?date={(start + dt.timedelta(days=7)).isoformat()}",
                "today_url": base,
                "view": "week",
            }
        )
        return ctx


class AgendaDayView(_AgendaBase):
    template_name = "agenda/day.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        day = _parse_date(self.request.GET.get("date"))
        buckets = self._events(day, day + dt.timedelta(days=1))
        today = timezone.localdate()
        base = reverse("agenda:day")

        ctx.update(
            {
                "day": day,
                "weekday_name": _weekday_name(day),
                "events": buckets.get(day, []),
                "is_today": day == today,
                "heading": f"{_weekday_name(day)} {day.isoformat()}",
                "prev_url": f"{base}?date={(day - dt.timedelta(days=1)).isoformat()}",
                "next_url": f"{base}?date={(day + dt.timedelta(days=1)).isoformat()}",
                "today_url": base,
                "view": "day",
            }
        )
        return ctx
