"""Transactional write operations for clients (docs/adr/0018, 0021).

django-auditlog records the detailed field-diff `LogEntry` for every Client
change (registered in ``clients.audit``); these services additionally emit a
plain-language `audit.AuditLog` event so the client profile's Activity tab has a
single, readable source.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from audit.events import log_event
from audit.models import AuditAction
from clients.models import Client, ClientStatus
from core.numbering import format_reference, next_number

NUMBER_SCOPE = "client"


def allocate_client_number() -> str:
    period = str(timezone.localdate().year)
    value = next_number(NUMBER_SCOPE, period=period)
    return format_reference("CL", value, period=period)


@transaction.atomic
def create_client(*, actor, data: dict, request=None) -> Client:
    client = Client(**data)
    client.client_number = allocate_client_number()
    client.created_by = actor
    client.updated_by = actor
    client.full_clean(exclude=["client_number"])
    client.save()
    log_event(request, AuditAction.CLIENT_CREATED, actor=actor, obj=client)
    return client


@transaction.atomic
def update_client(*, actor, client: Client, data: dict, request=None) -> Client:
    # `client` may already carry the new values (a ModelForm mutates its instance
    # during is_valid()), so diff against the persisted row, not the in-memory one.
    stored = Client.objects.get(pk=client.pk)
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return client  # no-op: don't touch the row or the audit trail

    for field, value in data.items():
        setattr(client, field, value)
    client.updated_by = actor
    client.full_clean(exclude=["client_number"])
    client.save()
    log_event(
        request,
        AuditAction.CLIENT_UPDATED,
        actor=actor,
        obj=client,
        changes={"fields": sorted(changed)},
    )
    return client


@transaction.atomic
def archive_client(*, actor, client: Client, request=None) -> Client:
    if client.status == ClientStatus.ARCHIVED:
        return client
    previous = client.status
    client.status = ClientStatus.ARCHIVED
    client.updated_by = actor
    client.save(update_fields=["status", "updated_by", "updated_at"])
    log_event(
        request,
        AuditAction.CLIENT_ARCHIVED,
        actor=actor,
        obj=client,
        changes={"status": [previous, ClientStatus.ARCHIVED]},
    )
    return client


@transaction.atomic
def restore_client(
    *, actor, client: Client, request=None, to_status: str = ClientStatus.ACTIVE
) -> Client:
    if client.status != ClientStatus.ARCHIVED:
        return client
    client.status = to_status
    client.updated_by = actor
    client.save(update_fields=["status", "updated_by", "updated_at"])
    log_event(
        request,
        AuditAction.CLIENT_RESTORED,
        actor=actor,
        obj=client,
        changes={"status": [ClientStatus.ARCHIVED, to_status]},
    )
    return client
