"""Permission-scoped read queries for clients (docs/adr/0019)."""

from __future__ import annotations

from clients.models import Client, ClientStatus, ClientType


def client_list(
    *,
    user,
    query: str = "",
    type: str = "",
    status: str = "",
    include_archived: bool = False,
):
    """Clients visible to ``user``, filtered. Always goes through ``for_user``."""
    qs = Client.objects.for_user(user).select_related("created_by")

    if query:
        qs = qs.search(query)
    if type in ClientType.values:
        qs = qs.filter(type=type)
    if status in ClientStatus.values:
        qs = qs.filter(status=status)
    elif not include_archived:
        qs = qs.active()

    return qs
