import pytest
from django.urls import reverse

from cases.models import Case, CaseParty, CaseStatus
from cases.tests.factories import CaseFactory, CaseTypeFactory
from clients.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


def test_list_requires_login(client):
    resp = client.get(reverse("cases:list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_list_renders_for_any_staff(client, finance_clerk):
    CaseFactory.create_batch(2)
    client.force_login(finance_clerk)
    resp = client.get(reverse("cases:list"))
    assert resp.status_code == 200
    assert resp.context["total_count"] == 2


def test_list_hides_closed_by_default(client, office_manager):
    CaseFactory(status=CaseStatus.NEW)
    CaseFactory(status=CaseStatus.CLOSED)
    client.force_login(office_manager)
    assert client.get(reverse("cases:list")).context["total_count"] == 1
    resp = client.get(reverse("cases:list"), {"status": CaseStatus.CLOSED})
    assert resp.context["total_count"] == 1


def test_list_paginates(client, office_manager):
    CaseFactory.create_batch(30)
    client.force_login(office_manager)
    resp = client.get(reverse("cases:list"))
    assert len(resp.context["cases"]) == 25
    assert resp.context["page_obj"].paginator.num_pages == 2


def test_detail_ok_and_missing_is_404(client, office_manager):
    c = CaseFactory()
    client.force_login(office_manager)
    assert client.get(reverse("cases:detail", args=[c.pk])).status_code == 200
    assert client.get(reverse("cases:detail", args=[999999])).status_code == 404


@pytest.mark.parametrize("tab", ["overview", "parties", "notes", "correspondence", "timeline"])
def test_detail_tabs_render(client, office_manager, tab):
    c = CaseFactory()
    client.force_login(office_manager)
    resp = client.get(reverse("cases:detail", args=[c.pk]), {"tab": tab})
    assert resp.status_code == 200
    assert resp.context["tab"] == tab


def test_detail_unknown_tab_falls_back_to_overview(client, office_manager):
    c = CaseFactory()
    client.force_login(office_manager)
    resp = client.get(reverse("cases:detail", args=[c.pk]), {"tab": "hearings"})
    assert resp.context["tab"] == "overview"


def test_create_generates_number_and_redirects(client, office_manager):
    ctype = CaseTypeFactory()
    cl = ClientFactory()
    client.force_login(office_manager)
    resp = client.post(
        reverse("cases:create"),
        {"title": "قضية جديدة", "type": ctype.pk, "client": cl.pk, "priority": "medium"},
    )
    assert resp.status_code == 302
    c = Case.objects.get(title="قضية جديدة")
    assert c.case_number.startswith("CS-")
    assert c.created_by == office_manager


def test_create_forbidden_for_finance_clerk(client, finance_clerk):
    ctype = CaseTypeFactory()
    cl = ClientFactory()
    client.force_login(finance_clerk)
    resp = client.post(
        reverse("cases:create"),
        {"title": "x", "type": ctype.pk, "client": cl.pk, "priority": "medium"},
    )
    assert resp.status_code == 403
    assert not Case.objects.exists()


def test_update_changes_fields(client, office_manager):
    c = CaseFactory(title="قديم")
    client.force_login(office_manager)
    resp = client.post(
        reverse("cases:update", args=[c.pk]),
        {"title": "جديد", "type": c.type_id, "client": c.client_id, "priority": c.priority},
    )
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.title == "جديد"
    assert c.updated_by == office_manager


def test_status_change_via_action(client, office_manager):
    c = CaseFactory(status=CaseStatus.NEW)
    client.force_login(office_manager)
    resp = client.post(reverse("cases:status", args=[c.pk]), {"status": CaseStatus.IN_PROGRESS})
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.status == CaseStatus.IN_PROGRESS


def test_status_change_get_not_allowed(client, office_manager):
    c = CaseFactory()
    client.force_login(office_manager)
    assert client.get(reverse("cases:status", args=[c.pk])).status_code == 405


def test_party_add_and_remove(client, office_manager):
    c = CaseFactory()
    client.force_login(office_manager)
    resp = client.post(
        reverse("cases:party_add", args=[c.pk]),
        {"party_role": "opponent", "name": "الخصم"},
    )
    assert resp.status_code == 302
    party = CaseParty.objects.get(case=c)
    resp = client.post(reverse("cases:party_remove", args=[c.pk, party.pk]))
    assert resp.status_code == 302
    assert not CaseParty.objects.filter(pk=party.pk).exists()


def test_note_add(client, paralegal):
    c = CaseFactory()
    client.force_login(paralegal)
    resp = client.post(
        reverse("cases:note_add", args=[c.pk]), {"kind": "general", "body": "ملاحظة"}
    )
    assert resp.status_code == 302
    assert c.notes.count() == 1


def test_edit_case_with_deactivated_type_keeps_value(client, office_manager):
    """A CaseType later set is_active=False must still be a valid choice for a
    case that already uses it — editing an unrelated field must not lock the case."""
    c = CaseFactory()
    c.type.is_active = False
    c.type.save()
    client.force_login(office_manager)
    resp = client.post(
        reverse("cases:update", args=[c.pk]),
        {"title": "عنوان جديد", "type": c.type_id, "client": c.client_id, "priority": c.priority},
    )
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.title == "عنوان جديد"
    assert c.type_id is not None


def test_edit_form_offers_current_inactive_type(client, office_manager):
    c = CaseFactory()
    c.type.is_active = False
    c.type.save()
    client.force_login(office_manager)
    form = client.get(reverse("cases:update", args=[c.pk])).context["form"]
    assert c.type in list(form.fields["type"].queryset)
