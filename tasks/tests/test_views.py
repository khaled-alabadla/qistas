import datetime as dt

import pytest
from django.urls import reverse

from cases.tests.factories import CaseFactory
from tasks.models import Deadline, DeadlineStatus, Task, TaskStatus
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db
TODAY = dt.date.today()


# ── Tasks ──────────────────────────────────────────────────
def test_task_list_requires_login(client):
    resp = client.get(reverse("tasks:list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_task_list_for_any_staff_hides_closed_and_deleted(client, finance_clerk):
    TaskFactory(status=TaskStatus.NEW)
    TaskFactory(status=TaskStatus.DONE)
    TaskFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    client.force_login(finance_clerk)
    assert client.get(reverse("tasks:list")).context["total_count"] == 1


def test_task_list_paginates_keeps_filter_on_page_2(client, office_manager):
    TaskFactory.create_batch(30, status=TaskStatus.NEW)
    TaskFactory(status=TaskStatus.DONE)
    client.force_login(office_manager)
    p1 = client.get(reverse("tasks:list"))
    assert len(p1.context["tasks"]) == 25 and p1.context["total_count"] == 30
    p2 = client.get(reverse("tasks:list"), {"page": "2"})
    assert p2.context["total_count"] == 30 and len(p2.context["tasks"]) == 5


def test_task_list_mine_filter(client, office_manager, lawyer):
    TaskFactory(assigned_to=office_manager)
    TaskFactory(assigned_to=lawyer)
    client.force_login(office_manager)
    resp = client.get(reverse("tasks:list"), {"mine": "on"})
    assert resp.context["total_count"] == 1


def test_task_list_overdue_filter(client, office_manager):
    TaskFactory(due_date=TODAY - dt.timedelta(days=2))
    TaskFactory(due_date=TODAY + dt.timedelta(days=2))
    client.force_login(office_manager)
    assert client.get(reverse("tasks:list"), {"overdue": "on"}).context["total_count"] == 1


def test_task_create_prefills_case(client, office_manager):
    case = CaseFactory()
    client.force_login(office_manager)
    form = client.get(reverse("tasks:create") + f"?case={case.pk}").context["form"]
    assert str(form.initial.get("case")) == str(case.pk)
    resp = client.post(
        reverse("tasks:create"),
        {"title": "مهمة جديدة", "priority": "high", "case": case.pk},
    )
    assert resp.status_code == 302
    assert Task.objects.get(title="مهمة جديدة").case_id == case.pk


def test_task_create_on_closed_case_via_query(client, office_manager):
    from cases.models import CaseStatus

    case = CaseFactory(status=CaseStatus.CLOSED)
    client.force_login(office_manager)
    url = reverse("tasks:create") + f"?case={case.pk}"
    form = client.get(url).context["form"]
    assert case in list(form.fields["case"].queryset)
    resp = client.post(url, {"title": "أرشفة الملف", "priority": "low", "case": case.pk})
    assert resp.status_code == 302
    assert Task.objects.get(title="أرشفة الملف").case_id == case.pk


def test_task_create_forbidden_for_finance_clerk(client, finance_clerk):
    client.force_login(finance_clerk)
    assert client.get(reverse("tasks:create")).status_code == 403
    resp = client.post(reverse("tasks:create"), {"title": "x", "priority": "low"})
    assert resp.status_code == 403
    assert not Task.objects.exists()


def test_task_status_action(client, paralegal):
    t = TaskFactory()
    client.force_login(paralegal)
    resp = client.post(reverse("tasks:status", args=[t.pk]), {"status": TaskStatus.DONE})
    assert resp.status_code == 302
    t.refresh_from_db()
    assert t.status == TaskStatus.DONE and t.completed_at is not None


def test_task_status_get_not_allowed(client, office_manager):
    t = TaskFactory()
    client.force_login(office_manager)
    assert client.get(reverse("tasks:status", args=[t.pk])).status_code == 405


def test_task_delete_is_soft_and_404_afterwards(client, office_manager):
    t = TaskFactory()
    client.force_login(office_manager)
    assert client.post(reverse("tasks:delete", args=[t.pk])).status_code == 302
    t.refresh_from_db()
    assert t.deleted_at is not None
    assert client.get(reverse("tasks:detail", args=[t.pk])).status_code == 404


def test_task_edit_keeps_archived_client(client, office_manager):
    from clients.models import ClientStatus
    from clients.tests.factories import ClientFactory

    cl = ClientFactory()
    t = TaskFactory(client=cl)
    cl.status = ClientStatus.ARCHIVED
    cl.save()
    client.force_login(office_manager)
    form = client.get(reverse("tasks:update", args=[t.pk])).context["form"]
    assert cl in list(form.fields["client"].queryset)


# ── Deadlines ──────────────────────────────────────────────
def test_deadline_crud_flow(client, office_manager):
    client.force_login(office_manager)
    resp = client.post(
        reverse("tasks:deadline_create"),
        {"title": "مهلة استئناف", "due_date": (TODAY + dt.timedelta(days=10)).isoformat()},
    )
    assert resp.status_code == 302
    d = Deadline.objects.get(title="مهلة استئناف")
    resp = client.post(
        reverse("tasks:deadline_status", args=[d.pk]), {"status": DeadlineStatus.MET}
    )
    assert resp.status_code == 302
    d.refresh_from_db()
    assert d.status == DeadlineStatus.MET


def test_deadline_list_hides_closed_by_default(client, office_manager):
    DeadlineFactory(status=DeadlineStatus.PENDING)
    DeadlineFactory(status=DeadlineStatus.MET)
    client.force_login(office_manager)
    assert client.get(reverse("tasks:deadlines")).context["total_count"] == 1


def test_deadline_detail_404_missing(client, office_manager):
    client.force_login(office_manager)
    assert client.get(reverse("tasks:deadline_detail", args=[999999])).status_code == 404
