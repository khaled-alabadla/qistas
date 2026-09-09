"""Permission-scoped read queries for cases (docs/adr/0019)."""

from __future__ import annotations

from django.db.models import OuterRef, Subquery
from django.utils import timezone

from cases.models import Case, CasePriority, CaseStatus


def _next_hearing_subquery():
    """Soonest still-scheduled future hearing datetime per case (docs/adr/0028) —
    derived, never stored. Imported lazily to avoid a cases→hearings import cycle."""
    from hearings.models import Hearing, HearingStatus

    return Subquery(
        Hearing.objects.filter(
            case=OuterRef("pk"),
            status=HearingStatus.SCHEDULED,
            scheduled_at__gte=timezone.now(),
        )
        .order_by("scheduled_at")
        .values("scheduled_at")[:1]
    )


def case_list(
    *,
    user,
    query: str = "",
    status: str = "",
    priority: str = "",
    type_id: str = "",
    lawyer_id: str = "",
    client_id: str = "",
    include_closed: bool = False,
):
    qs = Case.objects.for_user(user).select_related("type", "client", "assigned_lawyer", "court")
    qs = qs.annotate(next_hearing_at=_next_hearing_subquery())
    if query:
        qs = qs.search(query)
    if status in CaseStatus.values:
        qs = qs.filter(status=status)
    elif not include_closed:
        qs = qs.open()
    if priority in CasePriority.values:
        qs = qs.filter(priority=priority)
    if str(type_id).isdigit():
        qs = qs.filter(type_id=type_id)
    if str(lawyer_id).isdigit():
        qs = qs.filter(assigned_lawyer_id=lawyer_id)
    if str(client_id).isdigit():
        qs = qs.filter(client_id=client_id)
    return qs


def case_parties(case, *, lawyer_links=None):
    """Everyone connected to the case: primary client, office lawyers, and the
    explicit CaseParty rows (spec §26 الأطراف tab). Pass ``lawyer_links`` (a
    prefetched list) to avoid re-querying the through table."""
    rows = []
    rows.append(
        {
            "role": "الموكل",
            "name": case.client.display_name,
            "kind": "client",
            "url": ("clients:detail", case.client_id),
        }
    )
    if case.assigned_lawyer_id:
        rows.append(
            {
                "role": "المحامي المسؤول",
                "name": case.assigned_lawyer.get_full_name() or case.assigned_lawyer.email,
                "kind": "lawyer",
                "url": None,
            }
        )
    if lawyer_links is None:
        lawyer_links = case.lawyer_links.select_related("lawyer")
    for link in lawyer_links:
        rows.append(
            {
                "role": "محامٍ مساند",
                "name": link.lawyer.get_full_name() or link.lawyer.email,
                "kind": "lawyer",
                "url": None,
            }
        )
    for p in case.parties.all():
        rows.append(
            {
                "role": p.get_party_role_display(),
                "name": p.name,
                "kind": "party",
                "party_id": p.pk,
                "phone": p.phone,
                "notes": p.notes,
                "url": None,
            }
        )
    return rows
