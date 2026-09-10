import datetime as dt

import pytest
from django.utils import timezone

from cases.tests.factories import CaseFactory
from contracts.models import ContractStatus
from contracts.selectors import (
    calendar_items,
    case_contracts,
    client_contracts,
    contract_list,
    expiring_contracts,
)
from contracts.tests.factories import ContractFactory

pytestmark = pytest.mark.django_db


def _today():
    return dt.date.today()


def test_contract_list_search_and_filters(office_manager):
    a = ContractFactory(title="اتفاقية أتعاب مع شركة النور", contract_type="retainer")
    ContractFactory(title="عقد آخر", contract_type="lease")
    assert a in list(contract_list(user=office_manager, query="النور"))
    assert list(contract_list(user=office_manager, contract_type="retainer")) == [a]


def test_contract_list_hides_closed_unless_asked(office_manager):
    ContractFactory(status=ContractStatus.ACTIVE)
    ContractFactory(status=ContractStatus.EXPIRED)
    assert contract_list(user=office_manager).count() == 1
    assert contract_list(user=office_manager, include_closed=True).count() == 2
    assert contract_list(user=office_manager, status="expired").count() == 1


def test_case_and_client_contracts(office_manager):
    case = CaseFactory()
    c = ContractFactory(case=case, client=case.client)
    assert list(case_contracts(case)) == [c]
    assert list(client_contracts(case.client)) == [c]


def test_expiring_contracts_widget(office_manager):
    ContractFactory(status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=10))
    ContractFactory(status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=90))
    ContractFactory(status=ContractStatus.DRAFT, end_date=_today() + dt.timedelta(days=5))
    assert expiring_contracts(office_manager, days=30).count() == 1


def test_calendar_items_only_active_in_window(user):
    today = _today()
    ContractFactory(status=ContractStatus.ACTIVE, end_date=today + dt.timedelta(days=3))
    ContractFactory(status=ContractStatus.DRAFT, end_date=today + dt.timedelta(days=3))
    ContractFactory(status=ContractStatus.ACTIVE, end_date=today + dt.timedelta(days=40))

    start = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
    end = start + dt.timedelta(days=10)
    items = calendar_items(user, start, end)
    assert len(items) == 1
    assert items[0]["kind"] == "contract" and items[0]["all_day"] is True


def test_agenda_aggregator_includes_contracts(user):
    today = _today()
    ContractFactory(status=ContractStatus.ACTIVE, end_date=today + dt.timedelta(days=2))
    from agenda.selectors import calendar_events

    start = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
    end = start + dt.timedelta(days=7)
    kinds = {e["kind"] for e in calendar_events(user, start, end)}
    assert "contract" in kinds
