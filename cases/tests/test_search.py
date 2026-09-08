import pytest

from cases.selectors import case_list
from cases.tests.factories import CaseFactory

pytestmark = pytest.mark.django_db


def test_selector_search_and_filters(office_manager):
    a = CaseFactory(title="نزاع الوفاق", priority="high")
    CaseFactory(title="قضية أخرى", priority="low")
    assert a in list(case_list(user=office_manager, query="الوفاق"))
    assert list(case_list(user=office_manager, priority="high")) == [a]


def test_selector_excludes_closed_unless_asked(office_manager):
    CaseFactory(status="new")
    CaseFactory(status="closed")
    assert case_list(user=office_manager).count() == 1
    assert case_list(user=office_manager, include_closed=True).count() == 2
    assert case_list(user=office_manager, status="closed").count() == 1


def test_search_field_set_and_trgm_in_sync():
    from importlib import import_module

    from cases.models import SEARCH_FIELDS

    mod = import_module("cases.migrations.0003_case_search_indexes")
    assert tuple(sorted(mod.TRGM_COLUMNS)) == tuple(sorted(SEARCH_FIELDS))
