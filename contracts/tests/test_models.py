import datetime as dt
from importlib import import_module

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from contracts.models import SEARCH_FIELDS, Contract, ContractStatus
from contracts.tests.factories import ContractFactory

pytestmark = pytest.mark.django_db


def _today():
    return dt.date.today()


def test_str_and_defaults():
    c = ContractFactory(status=ContractStatus.DRAFT)
    assert c.contract_number in str(c)
    assert c.is_open is True


def test_for_user_denies_anon_allows_authed(user):
    ContractFactory.create_batch(2)
    assert Contract.objects.for_user(None).count() == 0
    assert Contract.objects.for_user(user).count() == 2


def test_end_before_start_rejected_by_clean():
    c = ContractFactory.build(start_date=_today(), end_date=_today() - dt.timedelta(days=1))
    with pytest.raises(ValidationError):
        c.clean()


def test_negative_value_rejected_by_clean():
    c = ContractFactory.build(value=-1)
    with pytest.raises(ValidationError):
        c.clean()


def test_value_check_constraint():
    client = ContractFactory().client
    with pytest.raises(IntegrityError), transaction.atomic():
        Contract.objects.create(
            contract_number="CT-2026-9001",
            title="x",
            client=client,
            start_date=_today(),
            value=-5,
        )


def test_end_before_start_check_constraint():
    client = ContractFactory().client
    with pytest.raises(IntegrityError), transaction.atomic():
        Contract.objects.create(
            contract_number="CT-2026-9002",
            title="x",
            client=client,
            start_date=_today(),
            end_date=_today() - dt.timedelta(days=1),
        )


def test_is_past_due_and_expiring_soon():
    active_past = ContractFactory(
        status=ContractStatus.ACTIVE, end_date=_today() - dt.timedelta(days=2)
    )
    active_soon = ContractFactory(
        status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=10)
    )
    active_far = ContractFactory(
        status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=200)
    )
    draft_soon = ContractFactory(
        status=ContractStatus.DRAFT, end_date=_today() + dt.timedelta(days=5)
    )

    assert active_past.is_past_due and not active_past.is_expiring_soon
    assert active_soon.is_expiring_soon and not active_soon.is_past_due
    assert not active_far.is_expiring_soon
    assert not draft_soon.is_expiring_soon  # only active contracts count
    assert active_soon.days_until_expiry == 10


def test_queryset_filters():
    ContractFactory(status=ContractStatus.ACTIVE, end_date=_today() - dt.timedelta(days=1))
    ContractFactory(status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=10))
    ContractFactory(status=ContractStatus.DRAFT, end_date=None)
    ContractFactory(status=ContractStatus.CANCELLED)

    assert Contract.objects.active().count() == 2
    assert Contract.objects.past_due().count() == 1
    assert Contract.objects.expiring_soon().count() == 1
    assert Contract.objects.open().count() == 3  # excludes cancelled only


def test_no_delete_permission():
    assert "delete" not in Contract._meta.default_permissions


def test_search_field_set_and_trgm_in_sync():
    mod = import_module("contracts.migrations.0002_contract_search_indexes")
    assert tuple(sorted(mod.TRGM_COLUMNS)) == tuple(sorted(SEARCH_FIELDS))
    # `notes` and `value` must NOT be searchable (spec §4).
    assert "notes" not in SEARCH_FIELDS and "value" not in SEARCH_FIELDS
