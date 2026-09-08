import pytest
from django.db import IntegrityError

from cases.models import Case, CaseEvent, CaseStatus
from cases.tests.factories import CaseFactory, CaseTypeFactory

pytestmark = pytest.mark.django_db


def test_for_user_returns_all_for_authenticated(office_manager, lawyer):
    CaseFactory.create_batch(3)
    assert Case.objects.for_user(office_manager).count() == 3
    assert Case.objects.for_user(lawyer).count() == 3


def test_for_user_returns_none_for_anonymous():
    from django.contrib.auth.models import AnonymousUser

    CaseFactory()
    assert Case.objects.for_user(AnonymousUser()).count() == 0


def test_open_excludes_terminal_statuses():
    CaseFactory(status=CaseStatus.NEW)
    CaseFactory(status=CaseStatus.CONCLUDED)
    CaseFactory(status=CaseStatus.CLOSED)
    assert Case.objects.open().count() == 1


def test_search_hits_title_and_court_number():
    by_title = CaseFactory(title="نزاع الوفاق التجاري")
    by_docket = CaseFactory(court_case_number="1234/2026")
    CaseFactory(title="قضية أخرى")
    assert by_title in list(Case.objects.search("الوفاق"))
    assert by_docket in list(Case.objects.search("1234/2026"))
    assert Case.objects.search("لا-يوجد-إطلاقا").count() == 0


def test_case_number_unique():
    CaseFactory(case_number="CS-2026-9999")
    with pytest.raises(IntegrityError):
        CaseFactory(case_number="CS-2026-9999")


def test_get_confidential_creates_row():
    c = CaseFactory()
    conf = c.get_confidential()
    assert conf.pk is not None
    assert conf.is_empty
    assert c.get_confidential().pk == conf.pk  # idempotent


def test_case_event_is_append_only():
    c = CaseFactory()
    ev = CaseEvent.objects.create(case=c, event_type="created", summary="x")
    with pytest.raises(PermissionError):
        ev.delete()
    with pytest.raises(PermissionError):
        CaseEvent.objects.all().delete()


def test_claim_amount_non_negative_constraint():
    with pytest.raises(IntegrityError):
        CaseFactory(claim_amount=-1)


def test_case_type_str():
    t = CaseTypeFactory(name="مدنية")
    assert str(t) == "مدنية"
