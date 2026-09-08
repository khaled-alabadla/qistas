import pytest
from django.db import IntegrityError, connection
from django.db.utils import DataError

from clients.models import Client, ClientStatus, ClientType
from clients.services import create_client
from clients.tests.factories import ClientFactory, CompanyClientFactory
from core.tests.utils import run_concurrently

pytestmark = pytest.mark.django_db


def test_create_allocates_sequential_client_number(office_manager):
    a = create_client(
        actor=office_manager,
        data={"type": ClientType.INDIVIDUAL, "full_name": "أحمد", "phone": "059"},
    )
    b = create_client(
        actor=office_manager,
        data={"type": ClientType.COMPANY, "company_name": "شركة", "phone": "059"},
    )
    assert a.client_number.startswith("CL-")
    assert a.client_number != b.client_number
    assert int(b.client_number.rsplit("-", 1)[1]) == int(a.client_number.rsplit("-", 1)[1]) + 1


def test_client_number_is_unique():
    ClientFactory(client_number="CL-2026-9999")
    with pytest.raises(IntegrityError):
        ClientFactory(client_number="CL-2026-9999")


def test_display_name():
    ind = ClientFactory(type=ClientType.INDIVIDUAL, full_name="محمود درويش", company_name="")
    co = CompanyClientFactory(company_name="شركة الوفاق")
    assert ind.display_name == "محمود درويش"
    assert co.display_name == "شركة الوفاق"


def test_individual_without_name_rejected_by_clean():
    from django.core.exceptions import ValidationError

    c = Client(type=ClientType.INDIVIDUAL, full_name="", phone="059")
    with pytest.raises(ValidationError):
        c.full_clean(exclude=["client_number"])


def test_name_matches_type_db_constraint():
    with pytest.raises((IntegrityError, DataError)):
        Client.objects.create(
            client_number="CL-2026-0500",
            type=ClientType.COMPANY,
            company_name="",
            full_name="",
            phone="059",
        )


def test_for_user_scoping(office_manager, user_factory):
    ClientFactory.create_batch(3)
    from django.contrib.auth.models import AnonymousUser

    assert Client.objects.for_user(AnonymousUser()).count() == 0
    qs = Client.objects.for_user(office_manager)
    assert qs.count() == 3
    assert getattr(qs, "_is_scoped", False) is True


def test_active_excludes_archived():
    ClientFactory(status=ClientStatus.ACTIVE)
    ClientFactory(status=ClientStatus.ARCHIVED)
    assert Client.objects.active().count() == 1


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_client_number_allocation(office_manager):
    if connection.vendor != "postgresql":
        pytest.skip("needs real row locking")
    n = 15

    def make():
        from django.db import connection as conn

        try:
            return create_client(
                actor=office_manager,
                data={"type": ClientType.INDIVIDUAL, "full_name": "x", "phone": "0"},
            ).client_number
        finally:
            conn.close()

    results = run_concurrently(make, n)
    numbers = [r for r in results if isinstance(r, str)]
    assert len(set(numbers)) == n, [r for r in results if not isinstance(r, str)]
