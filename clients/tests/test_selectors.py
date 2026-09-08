import pytest

from clients.models import ClientStatus, ClientType
from clients.selectors import client_list
from clients.tests.factories import ClientFactory, CompanyClientFactory
from core.querysets import assert_scoped

pytestmark = pytest.mark.django_db


def test_client_list_is_always_scoped(office_manager):
    ClientFactory.create_batch(2)
    qs = client_list(user=office_manager)
    assert_scoped(qs)  # must not raise
    assert getattr(qs, "_is_scoped", False) is True


def test_anonymous_gets_nothing():
    from django.contrib.auth.models import AnonymousUser

    ClientFactory.create_batch(3)
    assert client_list(user=AnonymousUser()).count() == 0


def test_filters_compose(office_manager):
    CompanyClientFactory(company_name="ألفا", status=ClientStatus.ACTIVE)
    CompanyClientFactory(company_name="بيتا", status=ClientStatus.PROSPECT)
    ClientFactory(full_name="ألفا شخص", status=ClientStatus.ACTIVE)

    r = client_list(user=office_manager, query="ألفا", type=ClientType.COMPANY)
    assert [c.company_name for c in r] == ["ألفا"]


def test_invalid_filter_values_are_ignored(office_manager):
    ClientFactory.create_batch(2)
    r = client_list(user=office_manager, type="bogus", status="bogus")
    assert r.count() == 2
