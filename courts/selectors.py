"""Permission-scoped read queries for courts (docs/adr/0019)."""

from __future__ import annotations

from courts.models import Court, CourtType


def court_list(
    *,
    user,
    query: str = "",
    type: str = "",
    include_inactive: bool = False,
):
    """Courts visible to ``user``, filtered. Always goes through ``for_user``."""
    qs = Court.objects.for_user(user)
    if query:
        qs = qs.search(query)
    if type in CourtType.values:
        qs = qs.filter(type=type)
    if not include_inactive:
        qs = qs.active()
    return qs
