import pytest
from django.urls import reverse

from clients.selectors import client_list
from clients.tests.factories import ClientFactory, CompanyClientFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def dataset(db):
    return {
        "name": ClientFactory(
            full_name="محمود أحمد درويش",
            national_id="905112233",
            phone="+970-599-100200",
            city="رام الله",
        ),
        "company": CompanyClientFactory(
            company_name="شركة الوفاق التجارية", registration_number="562-114-903", city="نابلس"
        ),
        "other": ClientFactory(full_name="سعاد نصر", phone="+970-598-777888", city="الخليل"),
    }


@pytest.mark.parametrize(
    "term,expected",
    [
        ("درويش", "name"),
        ("الوفاق", "company"),
        ("100200", "name"),
        ("نابلس", "company"),
    ],
)
def test_search_matches_expected_fields(dataset, office_manager, term, expected):
    results = list(client_list(user=office_manager, query=term))
    assert dataset[expected] in results


def test_search_never_matches_national_id(dataset, office_manager):
    results = client_list(user=office_manager, query="905112233")
    assert dataset["name"] not in list(results)
    assert results.count() == 0


def test_search_by_client_number(dataset, office_manager):
    num = dataset["name"].client_number
    assert dataset["name"] in list(client_list(user=office_manager, query=num))


def test_list_response_never_contains_national_id(client, office_manager, dataset):
    client.force_login(office_manager)
    body = client.get(reverse("clients:list")).content.decode()
    assert "905112233" not in body


def test_search_field_set_excludes_sensitive():
    from clients.models import SEARCH_FIELDS

    assert "national_id" not in SEARCH_FIELDS
    assert "registration_number" not in SEARCH_FIELDS


def test_trgm_columns_match_search_fields():
    """Every searched column must be trigram-indexed or the OR forces a seq scan."""
    from importlib import import_module

    from clients.models import SEARCH_FIELDS

    mod = import_module("clients.migrations.0002_client_search_indexes")
    assert tuple(sorted(mod.TRGM_COLUMNS)) == tuple(sorted(SEARCH_FIELDS))
