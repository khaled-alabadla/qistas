import pytest
from auditlog.models import LogEntry
from auditlog.registry import auditlog

from cases import services
from cases.models import Case, CaseConfidential, CaseParty
from cases.tests.factories import CaseFactory, CaseTypeFactory
from clients.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


def test_case_models_registered_with_auditlog():
    for model in (Case, CaseConfidential, CaseParty):
        assert auditlog.contains(model)


def test_case_create_writes_logentry(office_manager):
    case = services.create_case(
        actor=office_manager,
        data={
            "title": "قضية",
            "type": CaseTypeFactory(),
            "client": ClientFactory(),
            "priority": "medium",
        },
    )
    assert LogEntry.objects.get_for_object(case).exists()


def test_confidential_notes_masked_in_logentry(office_manager):
    case = CaseFactory()
    services.set_confidential(
        actor=office_manager,
        case=case,
        legal_notes="محتوى-قانوني-حساس",
        internal_notes="محتوى-داخلي-حساس",
    )
    for entry in LogEntry.objects.get_for_object(case.get_confidential()):
        blob = str(entry.changes)
        assert "محتوى-قانوني-حساس" not in blob
        assert "محتوى-داخلي-حساس" not in blob
