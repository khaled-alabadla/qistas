"""End-to-end HTTP smoke for the Phase 7 surface (contracts)."""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from contracts.models import ContractStatus
from contracts.tests.factories import ContractFactory

pytestmark = pytest.mark.django_db


def test_phase7_pages_render(client, office_manager):
    client.force_login(office_manager)
    case = CaseFactory()
    cl = ClientFactory()
    contract = ContractFactory(case=case, client=cl, status=ContractStatus.ACTIVE)
    urls = [
        reverse("contracts:list"),
        reverse("contracts:list") + "?q=&status=active&expiring=on",
        reverse("contracts:create"),
        reverse("contracts:create") + f"?case={case.pk}&client={cl.pk}",
        reverse("contracts:detail", args=[contract.pk]),
        reverse("contracts:update", args=[contract.pk]),
        reverse("cases:detail", args=[case.pk]) + "?tab=contracts",
        reverse("clients:detail", args=[cl.pk]),
        reverse("core:landing"),
        reverse("agenda:month"),
    ]
    for url in urls:
        assert client.get(url).status_code == 200, url


def test_expire_contracts_command_runs(office_manager):
    ContractFactory(status=ContractStatus.ACTIVE, end_date=dt.date.today() - dt.timedelta(days=1))
    call_command("expire_contracts", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_seed_demo_contracts_runs_outside_test_transaction():
    """The command allocates a contract number (``select_for_update``) and so
    must open its own ``transaction.atomic`` rather than lean on an ambient one
    (buglog bug-076 — only actually raises on PostgreSQL, but the decorator is
    the guard). Run here without the usual per-test transaction wrapper."""
    from clients.tests.factories import ClientFactory as _ClientFactory
    from contracts.models import Contract

    _ClientFactory.create_batch(3)
    call_command("seed_demo_contracts", verbosity=0)
    assert Contract.objects.exists()
