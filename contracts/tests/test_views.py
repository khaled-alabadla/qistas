import datetime as dt

import pytest
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.models import CaseStatus
from cases.tests.factories import CaseFactory
from clients.models import ClientStatus
from clients.tests.factories import ClientFactory
from contracts.models import Contract, ContractStatus
from contracts.tests.factories import ContractFactory

pytestmark = pytest.mark.django_db


def _today():
    return dt.date.today()


# ── list / detail ──────────────────────────────────────────
def test_list_requires_login(client):
    resp = client.get(reverse("contracts:list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_list_renders_for_any_staff_hides_closed_by_default(client, finance_clerk):
    ContractFactory(status=ContractStatus.ACTIVE)
    ContractFactory(status=ContractStatus.CANCELLED)
    client.force_login(finance_clerk)
    resp = client.get(reverse("contracts:list"))
    assert resp.status_code == 200
    assert resp.context["total_count"] == 1
    assert resp.context["can_manage"] is False


def test_list_paginates_and_keeps_scope_on_page_2(client, office_manager):
    ContractFactory.create_batch(30, status=ContractStatus.ACTIVE)
    client.force_login(office_manager)
    p1 = client.get(reverse("contracts:list"))
    assert len(p1.context["contracts"]) == 25 and p1.context["total_count"] == 30
    p2 = client.get(reverse("contracts:list"), {"page": "2"})
    assert len(p2.context["contracts"]) == 5 and p2.context["total_count"] == 30


def test_list_status_filter_and_expiring_toggle(client, office_manager):
    ContractFactory(status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=5))
    ContractFactory(status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=300))
    ContractFactory(status=ContractStatus.DRAFT)
    client.force_login(office_manager)
    assert client.get(reverse("contracts:list"), {"status": "draft"}).context["total_count"] == 1
    assert client.get(reverse("contracts:list"), {"expiring": "on"}).context["total_count"] == 1


def test_detail_404_for_missing(client, office_manager):
    client.force_login(office_manager)
    assert client.get(reverse("contracts:detail", args=[999999])).status_code == 404


# ── create ─────────────────────────────────────────────────
def test_create_requires_manage(client, paralegal):
    client.force_login(paralegal)
    assert client.get(reverse("contracts:create")).status_code == 403


def test_create_by_admin_clerk_allocates_number(client, admin_clerk):
    cl = ClientFactory()
    client.force_login(admin_clerk)
    resp = client.post(
        reverse("contracts:create"),
        {
            "title": "  اتفاقية تمثيل  ",
            "contract_type": "engagement",
            "client": cl.pk,
            "start_date": _today().isoformat(),
            "end_date": (_today() + dt.timedelta(days=90)).isoformat(),
            "value": "5000.00",
            "currency": "ILS",
            "status": "active",
            "description": "",
            "notes": "",
        },
    )
    assert resp.status_code == 302
    c = Contract.objects.get()
    assert c.contract_number.startswith("CT-")
    assert c.status == ContractStatus.ACTIVE
    assert c.created_by == admin_clerk
    assert AuditLog.objects.filter(action=AuditAction.CONTRACT_CREATED).exists()


def test_create_rejects_expired_status_choice(client, office_manager):
    cl = ClientFactory()
    client.force_login(office_manager)
    resp = client.post(
        reverse("contracts:create"),
        {
            "title": "x",
            "contract_type": "other",
            "client": cl.pk,
            "start_date": _today().isoformat(),
            "currency": "ILS",
            "status": "expired",
        },
    )
    assert resp.status_code == 200
    assert resp.context["form"].errors.get("status")


def test_create_rejects_end_before_start(client, office_manager):
    cl = ClientFactory()
    client.force_login(office_manager)
    resp = client.post(
        reverse("contracts:create"),
        {
            "title": "x",
            "contract_type": "other",
            "client": cl.pk,
            "start_date": _today().isoformat(),
            "end_date": (_today() - dt.timedelta(days=5)).isoformat(),
            "currency": "ILS",
            "status": "draft",
        },
    )
    assert resp.status_code == 200
    assert resp.context["form"].errors.get("end_date")
    assert not Contract.objects.exists()


def test_create_prefill_ignores_out_of_scope_ids(client, office_manager):
    client.force_login(office_manager)
    form = client.get(reverse("contracts:create") + "?client=999999&case=abc").context["form"]
    assert form.initial.get("client") is None


def test_create_mass_assignment_ignores_contract_number(client, office_manager):
    cl = ClientFactory()
    client.force_login(office_manager)
    client.post(
        reverse("contracts:create"),
        {
            "title": "y",
            "contract_type": "other",
            "client": cl.pk,
            "start_date": _today().isoformat(),
            "currency": "ILS",
            "status": "draft",
            "contract_number": "CT-1900-0001",
        },
    )
    c = Contract.objects.get()
    assert c.contract_number != "CT-1900-0001"


# ── edit ───────────────────────────────────────────────────
def test_edit_has_no_status_field_and_keeps_archived_client(client, office_manager):
    cl = ClientFactory()
    c = ContractFactory(client=cl)
    cl.status = ClientStatus.ARCHIVED
    cl.save()
    client.force_login(office_manager)
    form = client.get(reverse("contracts:update", args=[c.pk])).context["form"]
    assert "status" not in form.fields
    assert cl in list(form.fields["client"].queryset)


# ── status action ──────────────────────────────────────────
def test_status_action_gated_and_guards_terminal(client, office_manager, finance_clerk):
    c = ContractFactory(status=ContractStatus.DRAFT)

    client.force_login(finance_clerk)
    assert (
        client.post(reverse("contracts:status", args=[c.pk]), {"status": "active"}).status_code
        == 403
    )

    client.force_login(office_manager)
    client.post(reverse("contracts:status", args=[c.pk]), {"status": "cancelled"})
    c.refresh_from_db()
    assert c.status == ContractStatus.CANCELLED
    # cancelled is terminal — a further transition is rejected, status unchanged
    client.post(reverse("contracts:status", args=[c.pk]), {"status": "active"})
    c.refresh_from_db()
    assert c.status == ContractStatus.CANCELLED


# ── case integration ───────────────────────────────────────
def test_case_contracts_tab(client, office_manager):
    case = CaseFactory(status=CaseStatus.CLOSED)
    ContractFactory(case=case, title="عقد القضية")
    client.force_login(office_manager)
    resp = client.get(reverse("cases:detail", args=[case.pk]), {"tab": "contracts"})
    assert resp.status_code == 200
    assert list(resp.context["case_contracts"]) != []


def test_client_profile_contracts_card(client, office_manager):
    cl = ClientFactory()
    ContractFactory(client=cl)
    client.force_login(office_manager)
    resp = client.get(reverse("clients:detail", args=[cl.pk]))
    assert resp.status_code == 200
    assert list(resp.context["client_contracts"]) != []


def test_landing_expiring_widget(client, office_manager):
    ContractFactory(status=ContractStatus.ACTIVE, end_date=_today() + dt.timedelta(days=7))
    client.force_login(office_manager)
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 200
    assert resp.context["expiring_contracts_count"] == 1
