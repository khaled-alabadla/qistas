"""Privileged-notes isolation (docs/adr/0008, 0009)."""

import pytest
from auditlog.models import LogEntry
from django.urls import reverse

from cases import services
from cases.tests.factories import CaseFactory

pytestmark = pytest.mark.django_db

SECRET = "أسرار-الموكل-الخاصة-جدا"


def test_confidential_absent_from_detail_for_unprivileged(client, paralegal, office_manager):
    case = CaseFactory()
    services.set_confidential(
        actor=office_manager, case=case, legal_notes=SECRET, internal_notes=""
    )
    client.force_login(paralegal)
    body = client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert SECRET not in body
    assert "confidential" not in client.get(reverse("cases:detail", args=[case.pk])).context


def test_confidential_visible_to_privileged(client, lawyer, office_manager):
    case = CaseFactory()
    services.set_confidential(
        actor=office_manager, case=case, legal_notes=SECRET, internal_notes=""
    )
    client.force_login(lawyer)
    body = client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert SECRET in body


def test_confidential_never_in_timeline(client, office_manager):
    case = CaseFactory()
    services.set_confidential(
        actor=office_manager, case=case, legal_notes=SECRET, internal_notes=""
    )
    client.force_login(office_manager)
    body = client.get(reverse("cases:detail", args=[case.pk]), {"tab": "timeline"}).content.decode()
    assert SECRET not in body


def test_confidential_masked_in_auditlog_diff(office_manager):
    case = CaseFactory()
    services.set_confidential(
        actor=office_manager, case=case, legal_notes=SECRET, internal_notes="داخلي"
    )
    for entry in LogEntry.objects.all():
        assert SECRET not in str(entry.changes)


def test_update_via_view_persists(client, office_manager):
    case = CaseFactory()
    client.force_login(office_manager)
    resp = client.post(
        reverse("cases:confidential", args=[case.pk]),
        {"legal_notes": SECRET, "internal_notes": ""},
    )
    assert resp.status_code == 302
    assert case.get_confidential().legal_notes == SECRET


def test_activity_panel_hides_confidential_event_from_unprivileged(
    client, office_manager, lawyer, paralegal
):
    case = CaseFactory()
    services.set_confidential(
        actor=office_manager, case=case, legal_notes=SECRET, internal_notes=""
    )

    client.force_login(paralegal)
    ctx = client.get(reverse("cases:detail", args=[case.pk])).context
    assert "case.confidential_updated" not in [a.action for a in ctx["activity"]]

    client.force_login(lawyer)
    ctx = client.get(reverse("cases:detail", args=[case.pk])).context
    assert "case.confidential_updated" in [a.action for a in ctx["activity"]]


def test_reading_a_case_never_creates_a_confidential_row(client, lawyer):
    from cases.models import CaseConfidential

    case = CaseFactory()
    client.force_login(lawyer)
    client.get(reverse("cases:detail", args=[case.pk]))
    client.get(reverse("cases:confidential", args=[case.pk]))
    assert not CaseConfidential.objects.filter(case=case).exists()
