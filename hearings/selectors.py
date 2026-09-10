"""Permission-scoped read queries for hearings (docs/adr/0019)."""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from hearings.models import Hearing, HearingStatus, HearingType

_SELECT_RELATED = ("case", "case__client", "court", "lawyer")


def hearing_list(
    *,
    user,
    query: str = "",
    status: str = "",
    hearing_type: str = "",
    court_id: str = "",
    case_id: str = "",
    when: str = "upcoming",
):
    """Hearings visible to ``user``, filtered. Always goes through ``for_user``.

    ``when``: ``upcoming`` (default — still-scheduled, future), ``past``
    (scheduled_at already elapsed), or ``all``.
    """
    qs = Hearing.objects.for_user(user).select_related(*_SELECT_RELATED)
    if query:
        qs = qs.search(query)
    if status in HearingStatus.values:
        qs = qs.filter(status=status)
    if hearing_type in HearingType.values:
        qs = qs.filter(hearing_type=hearing_type)
    if str(court_id).isdigit():
        qs = qs.filter(court_id=court_id)
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)

    if when == "past":
        qs = qs.filter(scheduled_at__lt=timezone.now())
    elif when == "all":
        pass
    else:  # "upcoming" (the default for any unrecognised value)
        qs = qs.upcoming().order_by("scheduled_at")
    return qs


def case_hearings(case):
    """Every hearing for ``case``, newest first (case workspace §26 الجلسات tab)."""
    return (
        case.hearings.select_related("court", "lawyer", "created_by")
        .all()
        .order_by("-scheduled_at")
    )


def today_hearings(user):
    """Still-scheduled hearings whose ``scheduled_at`` falls today, in the office
    timezone (spec §19 'Today's Hearings')."""
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=1)
    return (
        Hearing.objects.for_user(user)
        .select_related(*_SELECT_RELATED)
        .filter(status=HearingStatus.SCHEDULED, scheduled_at__gte=start, scheduled_at__lt=end)
        .order_by("scheduled_at")
    )


def upcoming_hearings(user, *, days: int = 7):
    """Still-scheduled hearings in the next ``days`` days (dashboard attention)."""
    now = timezone.now()
    return (
        Hearing.objects.for_user(user)
        .select_related(*_SELECT_RELATED)
        .filter(
            status=HearingStatus.SCHEDULED,
            scheduled_at__gte=now,
            scheduled_at__lt=now + dt.timedelta(days=days),
        )
        .order_by("scheduled_at")
    )


def calendar_hearings(user, start, end):
    """Scheduled + held hearings whose ``scheduled_at`` falls in ``[start, end)``,
    for the agenda aggregator (docs/adr/0028)."""
    return (
        Hearing.objects.for_user(user)
        .select_related(*_SELECT_RELATED)
        .in_range(start, end)
        .exclude(status=HearingStatus.CANCELLED)
        .order_by("scheduled_at")
    )
