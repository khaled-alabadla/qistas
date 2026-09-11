import pytest
from django.urls import reverse

from clients.models import Client, ClientStatus, ClientType
from clients.tests.factories import ClientFactory, CompanyClientFactory

pytestmark = pytest.mark.django_db


def test_list_renders_for_any_staff(client, finance_clerk):
    ClientFactory.create_batch(2)
    client.force_login(finance_clerk)
    resp = client.get(reverse("clients:list"))
    assert resp.status_code == 200
    assert resp.context["total_count"] == 2


def test_list_requires_login(client):
    resp = client.get(reverse("clients:list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_list_filter_by_type(client, office_manager):
    ClientFactory()
    CompanyClientFactory()
    client.force_login(office_manager)
    resp = client.get(reverse("clients:list"), {"type": ClientType.COMPANY})
    assert resp.context["total_count"] == 1
    assert resp.context["clients"][0].type == ClientType.COMPANY


def test_list_hides_archived_by_default_but_filter_shows(client, office_manager):
    ClientFactory(status=ClientStatus.ACTIVE)
    ClientFactory(status=ClientStatus.ARCHIVED)
    client.force_login(office_manager)
    assert client.get(reverse("clients:list")).context["total_count"] == 1
    resp = client.get(reverse("clients:list"), {"status": ClientStatus.ARCHIVED})
    assert resp.context["total_count"] == 1
    assert resp.context["clients"][0].status == ClientStatus.ARCHIVED


def test_list_paginates(client, office_manager):
    ClientFactory.create_batch(30)
    client.force_login(office_manager)
    resp = client.get(reverse("clients:list"))
    assert len(resp.context["clients"]) == 25
    assert resp.context["page_obj"].paginator.num_pages == 2


def test_detail_ok_and_missing_is_404(client, office_manager):
    c = ClientFactory()
    client.force_login(office_manager)
    assert client.get(reverse("clients:detail", args=[c.pk])).status_code == 200
    assert client.get(reverse("clients:detail", args=[999999])).status_code == 404


def test_create_generates_number_and_redirects(client, office_manager):
    client.force_login(office_manager)
    resp = client.post(
        reverse("clients:create"),
        {
            "type": ClientType.INDIVIDUAL,
            "full_name": "سعيد سالم",
            "phone": "+970-599-111222",
            "status": ClientStatus.ACTIVE,
        },
    )
    assert resp.status_code == 302
    c = Client.objects.get(full_name="سعيد سالم")
    assert c.client_number.startswith("CL-")
    assert c.created_by == office_manager


def test_create_validation_error_rerenders(client, office_manager):
    client.force_login(office_manager)
    resp = client.post(
        reverse("clients:create"),
        {"type": ClientType.COMPANY, "company_name": "", "phone": "059"},
    )
    assert resp.status_code == 200
    assert "company_name" in resp.context["form"].errors
    assert not Client.objects.exists()


def test_update_changes_fields(client, office_manager):
    c = ClientFactory(city="نابلس")
    client.force_login(office_manager)
    resp = client.post(
        reverse("clients:update", args=[c.pk]),
        {
            "type": c.type,
            "full_name": c.full_name,
            "phone": c.phone,
            "city": "رام الله",
            "status": c.status,
        },
    )
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.city == "رام الله"
    assert c.updated_by == office_manager
    assert c.client_number  # unchanged / preserved


def test_update_cannot_smuggle_a_status_change(client, office_manager):
    """Status only changes through archive/restore — never the general edit
    form, or a save could silently archive a client with no `CLIENT_ARCHIVED`
    audit event and no transition guard (Phase 12 hardening)."""
    c = ClientFactory(status=ClientStatus.ACTIVE, city="نابلس")
    client.force_login(office_manager)
    resp = client.post(
        reverse("clients:update", args=[c.pk]),
        {
            "type": c.type,
            "full_name": c.full_name,
            "phone": c.phone,
            "city": "رام الله",
            "status": ClientStatus.ARCHIVED,  # attempted smuggling
        },
    )
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.city == "رام الله"  # the real edit still applies
    assert c.status == ClientStatus.ACTIVE  # status is untouched


def test_edit_form_never_renders_a_status_field(client, office_manager):
    c = ClientFactory()
    client.force_login(office_manager)
    resp = client.get(reverse("clients:update", args=[c.pk]))
    assert resp.status_code == 200
    assert "status" not in resp.context["form"].fields


def test_archive_then_restore(client, office_manager):
    c = ClientFactory(status=ClientStatus.ACTIVE)
    client.force_login(office_manager)

    assert client.get(reverse("clients:archive", args=[c.pk])).status_code == 405  # POST only
    resp = client.post(reverse("clients:archive", args=[c.pk]))
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.status == ClientStatus.ARCHIVED

    client.post(reverse("clients:restore", args=[c.pk]))
    c.refresh_from_db()
    assert c.status == ClientStatus.ACTIVE
