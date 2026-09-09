import pytest
from django.urls import reverse

from cases.tests.factories import CourtFactory
from courts.models import Court

pytestmark = pytest.mark.django_db


def test_list_requires_login(client):
    resp = client.get(reverse("courts:list"))
    assert resp.status_code == 302


def test_list_renders_for_any_staff(client, finance_clerk):
    CourtFactory(name="أ", city="ب")
    CourtFactory(name="ج", city="د")
    client.force_login(finance_clerk)
    resp = client.get(reverse("courts:list"))
    assert resp.status_code == 200
    assert resp.context["total_count"] == 2


def test_list_hides_inactive_by_default(client, office_manager):
    CourtFactory(name="نشطة", city="س")
    CourtFactory(name="معطلة", city="ع", is_active=False)
    client.force_login(office_manager)
    assert client.get(reverse("courts:list")).context["total_count"] == 1
    resp = client.get(reverse("courts:list"), {"include_inactive": "on"})
    assert resp.context["total_count"] == 2


def test_list_search(client, office_manager):
    CourtFactory(name="محكمة بداية أريحا", city="أريحا")
    CourtFactory(name="محكمة صلح جنين", city="جنين")
    client.force_login(office_manager)
    resp = client.get(reverse("courts:list"), {"q": "أريحا"})
    assert resp.context["total_count"] == 1


def test_create_requires_manage(client, lawyer):
    client.force_login(lawyer)
    assert client.get(reverse("courts:create")).status_code == 403


def test_create_by_office_manager(client, office_manager):
    client.force_login(office_manager)
    resp = client.post(
        reverse("courts:create"),
        {"name": "محكمة جديدة", "type": "first_instance", "city": "نابلس", "is_active": "on"},
    )
    assert resp.status_code == 302
    assert Court.objects.filter(name="محكمة جديدة").exists()


def test_update_and_toggle_active(client, office_manager):
    court = CourtFactory(name="أ", city="ب")
    client.force_login(office_manager)
    resp = client.post(
        reverse("courts:update", args=[court.pk]),
        {"name": "أ", "type": court.type, "city": "ب", "phone": "02-1112223", "is_active": "on"},
    )
    assert resp.status_code == 302
    court.refresh_from_db()
    assert court.phone == "02-1112223"

    resp = client.post(reverse("courts:set_active", args=[court.pk]), {"is_active": "0"})
    assert resp.status_code == 302
    court.refresh_from_db()
    assert court.is_active is False


def test_detail_404_for_missing(client, office_manager):
    client.force_login(office_manager)
    assert client.get(reverse("courts:detail", args=[999999])).status_code == 404
