"""Permission-scoped read queries for contracts (docs/adr/0019, 0028, 0031)."""

from __future__ import annotations

import datetime as dt

from django.urls import reverse
from django.utils import timezone

from contracts.models import Contract, ContractStatus, ContractType

_SELECT = ("client", "case", "created_by")


def contract_list(
    *,
    user,
    query: str = "",
    status: str = "",
    contract_type: str = "",
    case_id: str = "",
    client_id: str = "",
    expiring_soon: bool = False,
    include_closed: bool = False,
):
    qs = Contract.objects.for_user(user).select_related(*_SELECT)
    if query:
        qs = qs.search(query)
    if status in ContractStatus.values:
        qs = qs.filter(status=status)
    elif not include_closed:
        qs = qs.open()
    if contract_type in ContractType.values:
        qs = qs.filter(contract_type=contract_type)
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)
    if str(client_id).isdigit():
        qs = qs.filter(client_id=client_id)
    if expiring_soon:
        qs = qs.expiring_soon()
    return qs


def case_contracts(case):
    """Every contract for ``case`` (case workspace العقود tab)."""
    return case.contracts.select_related("client", "created_by").order_by("-created_at")


def client_contracts(client):
    return client.contracts.select_related("case", "created_by").order_by("-created_at")


def expiring_contracts(user, *, days: int = 30):
    """Active contracts due to lapse within ``days`` — landing widget + calendar."""
    return (
        Contract.objects.for_user(user)
        .expiring_soon(within_days=days)
        .select_related("client", "case")
        .order_by("end_date")
    )


# ── Calendar (agenda aggregator — docs/adr/0028) ────────────
def _combine(d: dt.date) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(d, dt.time.min), timezone.get_current_timezone())


def _contract_event(c: Contract) -> dict:
    return {
        "start": _combine(c.end_date),
        "title": f"{c.contract_number} — {c.title}",
        "kind": "contract",
        "all_day": True,
        "status": c.status,
        "done": False,
        "url": reverse("contracts:detail", args=[c.pk]),
        "meta": {
            "client": c.client.display_name if c.client_id else "",
            "case_title": c.case.title if c.case_id else "",
            "past_due": c.is_past_due,
        },
    }


def calendar_items(user, start, end) -> list[dict]:
    """One all-day event per **active** contract whose ``end_date`` falls in
    ``[start, end)`` — the "Contract expirations" calendar source (spec §33)."""
    contracts = (
        Contract.objects.for_user(user)
        .active()
        .filter(
            end_date__isnull=False,
            end_date__gte=start.date(),
            end_date__lt=end.date(),
        )
        .select_related("client", "case")
    )
    return [_contract_event(c) for c in contracts]
