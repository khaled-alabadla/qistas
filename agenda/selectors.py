"""
The agenda is a **derived-event aggregator**, not a model (docs/adr/0028).

``calendar_events(user, start, end)`` returns a normalised, time-ordered list of
event dicts. In Phase 4 the only source is ``hearings``; later phases add tasks,
deadlines and contract expirations by extending this one function (spec §33).
Every event carries a ``url`` back to its source entity.
"""

from __future__ import annotations

from django.urls import reverse

from hearings.models import HearingStatus
from hearings.selectors import calendar_hearings


def _hearing_event(h) -> dict:
    return {
        "start": h.scheduled_at,
        "title": f"{h.case.case_number} — {h.get_hearing_type_display()}",
        "kind": "hearing",
        "status": h.status,
        "done": h.status == HearingStatus.HELD,
        "url": reverse("hearings:detail", args=[h.pk]),
        "meta": {
            "case_title": h.case.title,
            "court": h.court.name if h.court else "",
            "room": h.room,
        },
    }


def calendar_events(user, start, end) -> list[dict]:
    """All calendar events for ``user`` in ``[start, end)`` (aware datetimes).

    Phase 4 source = hearings; Phase 5 adds tasks + deadlines (docs/adr/0028,
    0029). Later phases extend by appending another source here.
    """
    from tasks.selectors import calendar_items

    events = [_hearing_event(h) for h in calendar_hearings(user, start, end)]
    events += calendar_items(user, start, end)
    events.sort(key=lambda e: e["start"])
    return events
