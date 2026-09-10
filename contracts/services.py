"""
Transactional writes for contracts (docs/adr/0018, 0021, 0031).

Every mutation writes an ``audit.AuditLog`` event carrying **metadata only**
(``contract_number`` / ``title`` / ``contract_type`` / ``status`` / changed
field names — never ``notes`` / ``description`` / ``value`` bodies, ADR-0009). A
**case-linked** contract also records a ``CaseEvent`` on the case timeline
(spec §26) on create + status change; metadata edits do not (same rule as
documents).

``status`` moves only through :func:`change_contract_status` (guarded
transitions; ``cancelled`` is terminal) or the idempotent
:func:`expire_due_contracts` scan — it is never in the edit form's ``EDITABLE``
set.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from audit.events import log_event
from audit.models import AuditAction
from cases.models import CaseEventType
from cases.services import record_case_event
from contracts.models import Contract, ContractStatus
from core.numbering import format_reference, next_number

NUMBER_SCOPE = "contract"

EDITABLE = (
    "title",
    "contract_type",
    "client",
    "case",
    "start_date",
    "end_date",
    "value",
    "currency",
    "description",
    "notes",
)

# Reachable manual transitions. `cancelled` is terminal (docs/adr/0031).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ContractStatus.DRAFT: {ContractStatus.ACTIVE, ContractStatus.CANCELLED},
    ContractStatus.ACTIVE: {
        ContractStatus.DRAFT,
        ContractStatus.EXPIRED,
        ContractStatus.CANCELLED,
    },
    ContractStatus.EXPIRED: {ContractStatus.ACTIVE, ContractStatus.CANCELLED},
    ContractStatus.CANCELLED: set(),
}


def allocate_contract_number() -> str:
    period = str(timezone.localdate().year)
    return format_reference("CT", next_number(NUMBER_SCOPE, period=period), period=period)


def can_transition(current: str, new: str) -> bool:
    return new in _ALLOWED_TRANSITIONS.get(current, set())


def _label(field: str, value) -> str:
    try:
        return dict(Contract._meta.get_field(field).choices)[value]
    except Exception:
        return str(value)


def _audit_meta(contract: Contract) -> dict:
    return {
        "contract_number": contract.contract_number,
        "title": contract.title,
        "contract_type": contract.contract_type,
        "status": contract.status,
    }


@transaction.atomic
def create_contract(*, actor, data: dict, request=None) -> Contract:
    data = {k: v for k, v in data.items() if k in EDITABLE or k == "status"}
    status = data.pop("status", ContractStatus.DRAFT)
    if status not in {ContractStatus.DRAFT, ContractStatus.ACTIVE}:
        status = ContractStatus.DRAFT

    contract = Contract(**data)
    contract.status = status
    contract.contract_number = allocate_contract_number()
    contract.created_by = actor
    contract.updated_by = actor
    contract.full_clean(exclude=["contract_number", "created_by", "updated_by"])
    contract.save()

    if contract.case_id:
        record_case_event(
            contract.case,
            CaseEventType.CONTRACT_ADDED,
            f"عقد جديد: {contract.contract_number} — {contract.title}",
            actor=actor,
            contract_id=contract.pk,
        )
    log_event(
        request,
        AuditAction.CONTRACT_CREATED,
        actor=actor,
        obj=contract,
        changes=_audit_meta(contract),
    )
    return contract


@transaction.atomic
def update_contract(*, actor, contract: Contract, data: dict, request=None) -> Contract:
    data = {k: v for k, v in data.items() if k in EDITABLE}
    stored = Contract.objects.select_related("client", "case").get(pk=contract.pk)
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return contract
    for field, value in data.items():
        setattr(contract, field, value)
    contract.updated_by = actor
    contract.full_clean(exclude=["contract_number", "created_by", "updated_by"])
    contract.save()
    log_event(
        request,
        AuditAction.CONTRACT_UPDATED,
        actor=actor,
        obj=contract,
        changes={"fields": sorted(changed)},
    )
    return contract


@transaction.atomic
def change_contract_status(*, actor, contract: Contract, new_status: str, request=None) -> Contract:
    if contract.status == new_status:
        return contract
    if not can_transition(contract.status, new_status):
        from django.core.exceptions import ValidationError

        raise ValidationError(_transition_error(contract.status, new_status))
    previous = contract.status
    contract.status = new_status
    contract.updated_by = actor
    contract.save(update_fields=["status", "updated_by", "updated_at"])

    if contract.case_id:
        record_case_event(
            contract.case,
            CaseEventType.CONTRACT_STATUS_CHANGED,
            f"عقد «{contract.contract_number}»: {_label('status', previous)} ← "
            f"{_label('status', new_status)}",
            actor=actor,
            contract_id=contract.pk,
        )
    log_event(
        request,
        AuditAction.CONTRACT_STATUS_CHANGED,
        actor=actor,
        obj=contract,
        changes={"status": [previous, new_status]},
    )
    return contract


def _transition_error(current: str, new: str) -> str:
    return f"انتقال غير مسموح: {_label('status', current)} ← {_label('status', new)}"


@transaction.atomic
def expire_due_contracts(*, actor=None, request=None, today=None) -> int:
    """Flip every ``active`` contract whose ``end_date`` has passed to
    ``expired``. Idempotent — safe to run on a cron (docs/adr/0005,
    architecture §12). Returns the number of rows changed.
    """
    today = today or timezone.localdate()
    due = Contract.objects.filter(
        status=ContractStatus.ACTIVE,
        end_date__isnull=False,
        end_date__lt=today,
    ).select_related("case")
    count = 0
    for contract in due:
        previous = contract.status
        contract.status = ContractStatus.EXPIRED
        contract.updated_by = actor
        contract.save(update_fields=["status", "updated_by", "updated_at"])
        if contract.case_id:
            record_case_event(
                contract.case,
                CaseEventType.CONTRACT_STATUS_CHANGED,
                f"عقد «{contract.contract_number}»: {_label('status', previous)} ← "
                f"{_label('status', ContractStatus.EXPIRED)} (انتهاء تلقائي)",
                actor=actor,
                contract_id=contract.pk,
            )
        log_event(
            request,
            AuditAction.CONTRACT_STATUS_CHANGED,
            actor=actor,
            obj=contract,
            changes={"status": [previous, ContractStatus.EXPIRED], "auto": True},
        )
        count += 1
    return count
