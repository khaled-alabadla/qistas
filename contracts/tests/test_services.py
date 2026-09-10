import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from audit.models import AuditAction, AuditLog
from cases.models import CaseEventType
from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from contracts import services
from contracts.models import ContractStatus
from contracts.tests.factories import ContractFactory

pytestmark = pytest.mark.django_db


def _today():
    return dt.date.today()


def _data(**over):
    base = {
        "title": "اتفاقية تمثيل",
        "contract_type": "engagement",
        "client": ClientFactory(),
        "case": None,
        "start_date": _today(),
        "end_date": _today() + dt.timedelta(days=90),
        "value": 5000,
        "currency": "ILS",
        "description": "",
        "notes": "سري",
        "status": ContractStatus.DRAFT,
    }
    base.update(over)
    return base


def test_create_allocates_number_and_audits_metadata_only(office_manager):
    case = CaseFactory()
    contract = services.create_contract(
        actor=office_manager, data=_data(case=case, notes="لا تُدرج في السجل")
    )
    assert contract.contract_number.startswith("CT-")
    assert contract.created_by == office_manager
    assert case.events.filter(event_type=CaseEventType.CONTRACT_ADDED).exists()

    log = AuditLog.objects.get(action=AuditAction.CONTRACT_CREATED, entity_id=str(contract.pk))
    assert set(log.changes) == {"contract_number", "title", "contract_type", "status"}
    assert "لا تُدرج" not in str(log.changes)  # notes body never audited


def test_create_without_case_has_no_case_event(office_manager):
    services.create_contract(actor=office_manager, data=_data())
    assert AuditLog.objects.filter(action=AuditAction.CONTRACT_CREATED).count() == 1


def test_create_clamps_status_to_draft_or_active(office_manager):
    c = services.create_contract(actor=office_manager, data=_data(status=ContractStatus.EXPIRED))
    assert c.status == ContractStatus.DRAFT


def test_update_metadata_diffs_and_audits(office_manager):
    contract = ContractFactory(title="قديم")
    services.update_contract(
        actor=office_manager, contract=contract, data={"title": "جديد", "value": 99}
    )
    contract.refresh_from_db()
    assert contract.title == "جديد"
    log = AuditLog.objects.get(action=AuditAction.CONTRACT_UPDATED)
    assert set(log.changes["fields"]) == {"title", "value"}


def test_update_noop(office_manager):
    contract = ContractFactory(title="ثابت")
    services.update_contract(actor=office_manager, contract=contract, data={"title": "ثابت"})
    assert not AuditLog.objects.filter(action=AuditAction.CONTRACT_UPDATED).exists()


def test_update_cannot_touch_status(office_manager):
    contract = ContractFactory(status=ContractStatus.DRAFT)
    services.update_contract(
        actor=office_manager, contract=contract, data={"status": ContractStatus.ACTIVE}
    )
    contract.refresh_from_db()
    assert contract.status == ContractStatus.DRAFT


def test_status_transition_guarded_and_cancelled_is_terminal(office_manager):
    case = CaseFactory()
    contract = ContractFactory(status=ContractStatus.DRAFT, case=case)

    services.change_contract_status(
        actor=office_manager, contract=contract, new_status=ContractStatus.ACTIVE
    )
    contract.refresh_from_db()
    assert contract.status == ContractStatus.ACTIVE
    assert case.events.filter(event_type=CaseEventType.CONTRACT_STATUS_CHANGED).exists()

    services.change_contract_status(
        actor=office_manager, contract=contract, new_status=ContractStatus.CANCELLED
    )
    contract.refresh_from_db()
    assert contract.status == ContractStatus.CANCELLED

    with pytest.raises(ValidationError):
        services.change_contract_status(
            actor=office_manager, contract=contract, new_status=ContractStatus.ACTIVE
        )


def test_expire_due_contracts_is_idempotent(office_manager):
    due = ContractFactory(
        status=ContractStatus.ACTIVE,
        case=CaseFactory(),
        end_date=_today() - dt.timedelta(days=1),
    )
    not_due = ContractFactory(
        status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=5)
    )
    draft_past = ContractFactory(
        status=ContractStatus.DRAFT, end_date=_today() - dt.timedelta(days=10)
    )

    changed = services.expire_due_contracts()
    assert changed == 1
    due.refresh_from_db()
    not_due.refresh_from_db()
    draft_past.refresh_from_db()
    assert due.status == ContractStatus.EXPIRED
    assert not_due.status == ContractStatus.ACTIVE
    assert draft_past.status == ContractStatus.DRAFT  # scan only touches active

    assert services.expire_due_contracts() == 0
    assert AuditLog.objects.filter(action=AuditAction.CONTRACT_STATUS_CHANGED).count() == 1
    assert due.case.events.filter(event_type=CaseEventType.CONTRACT_STATUS_CHANGED).count() == 1
