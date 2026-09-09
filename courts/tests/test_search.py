import pytest

from cases.tests.factories import CourtFactory
from courts.selectors import court_list

pytestmark = pytest.mark.django_db


def test_selector_search_and_type_filter(office_manager):
    a = CourtFactory(name="محكمة بداية سلفيت", city="سلفيت", type="first_instance")
    CourtFactory(name="محكمة صلح قلقيلية", city="قلقيلية", type="conciliation")
    assert a in list(court_list(user=office_manager, query="سلفيت"))
    assert list(court_list(user=office_manager, type="conciliation")) != [a]


def test_selector_excludes_inactive_unless_asked(office_manager):
    CourtFactory(name="نشطة", city="س")
    CourtFactory(name="معطلة", city="ع", is_active=False)
    assert court_list(user=office_manager).count() == 1
    assert court_list(user=office_manager, include_inactive=True).count() == 2


def test_search_field_set_and_trgm_in_sync():
    from importlib import import_module

    from courts.models import SEARCH_FIELDS

    mod = import_module("courts.migrations.0003_court_search_indexes")
    assert tuple(sorted(mod.TRGM_COLUMNS)) == tuple(sorted(SEARCH_FIELDS))
