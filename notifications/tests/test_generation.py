"""
Every Phase 11 trigger: correct recipient, correct target, idempotency, and the
finance side-channel guard (spec Phase 11 §13–14, docs/adr/0035).
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from cases.tests.factories import CaseFactory
from contracts.models import ContractStatus
from contracts.tests.factories import ContractFactory
from finance.models import Invoice
from finance.tests.factories import issued_invoice
from hearings.tests.factories import HearingFactory
from notifications import generation
from notifications.models import Notification, NotificationCategory
from tasks.models import TaskStatus
from tasks.tests.factories import DeadlineFactory, TaskFactory

pytestmark = pytest.mark.django_db


# ── Hearing approaching ────────────────────────────────────
def test_hearing_upcoming_notifies_the_case_team(role_user):
    lawyer = role_user("lawyer")
    other_lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    h = HearingFactory(case=case, scheduled_at=timezone.now() + dt.timedelta(days=2))

    created = generation.scan_upcoming_hearings()
    assert created == 1

    n = Notification.objects.get(recipient=lawyer)
    assert n.category == NotificationCategory.HEARING_UPCOMING
    assert n.entity_type == "hearings.hearing"
    assert n.entity_id == str(h.pk)
    assert f"/hearings/{h.pk}/" in n.url
    assert not Notification.objects.filter(recipient=other_lawyer).exists()


def test_hearing_outside_window_is_ignored(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    HearingFactory(case=case, scheduled_at=timezone.now() + dt.timedelta(days=30))
    assert generation.scan_upcoming_hearings() == 0


def test_hearing_scan_is_idempotent(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    HearingFactory(case=case, scheduled_at=timezone.now() + dt.timedelta(days=1))

    assert generation.scan_upcoming_hearings() == 1
    assert generation.scan_upcoming_hearings() == 0
    assert Notification.objects.filter(recipient=lawyer).count() == 1


def test_rescheduling_produces_one_fresh_notification(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    h = HearingFactory(case=case, scheduled_at=timezone.now() + dt.timedelta(days=1))
    generation.scan_upcoming_hearings()

    h.scheduled_at = timezone.now() + dt.timedelta(days=2)
    h.save(update_fields=["scheduled_at"])
    assert generation.scan_upcoming_hearings() == 1
    assert Notification.objects.filter(recipient=lawyer).count() == 2


def test_hearing_without_a_team_falls_back_to_office_manager(role_user):
    om = role_user("office_manager")
    case = CaseFactory(assigned_lawyer=None)
    HearingFactory(case=case, scheduled_at=timezone.now() + dt.timedelta(days=1))

    generation.scan_upcoming_hearings()
    assert Notification.objects.filter(recipient=om).count() == 1


# ── Task overdue ───────────────────────────────────────────
def test_task_overdue_notifies_the_assignee(role_user):
    lawyer = role_user("lawyer")
    t = TaskFactory(
        assigned_to=lawyer,
        due_date=dt.date.today() - dt.timedelta(days=2),
        status=TaskStatus.NEW,
    )
    assert generation.scan_overdue_tasks() == 1
    n = Notification.objects.get(recipient=lawyer)
    assert n.category == NotificationCategory.TASK_OVERDUE
    assert n.entity_id == str(t.pk)


def test_task_not_overdue_is_ignored(role_user):
    lawyer = role_user("lawyer")
    TaskFactory(assigned_to=lawyer, due_date=dt.date.today() + dt.timedelta(days=2))
    assert generation.scan_overdue_tasks() == 0


def test_done_task_is_ignored(role_user):
    lawyer = role_user("lawyer")
    TaskFactory(
        assigned_to=lawyer,
        due_date=dt.date.today() - dt.timedelta(days=2),
        status=TaskStatus.DONE,
    )
    assert generation.scan_overdue_tasks() == 0


def test_task_scan_idempotent(role_user):
    lawyer = role_user("lawyer")
    TaskFactory(assigned_to=lawyer, due_date=dt.date.today() - dt.timedelta(days=1))
    assert generation.scan_overdue_tasks() == 1
    assert generation.scan_overdue_tasks() == 0


# ── Deadline approaching ───────────────────────────────────
def test_deadline_approaching_notifies_case_team(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    d = DeadlineFactory(case=case, due_date=dt.date.today() + dt.timedelta(days=3))
    assert generation.scan_approaching_deadlines() == 1
    n = Notification.objects.get(recipient=lawyer)
    assert n.category == NotificationCategory.DEADLINE_APPROACHING
    assert n.entity_id == str(d.pk)


def test_overdue_deadline_still_notified(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    DeadlineFactory(case=case, due_date=dt.date.today() - dt.timedelta(days=1))
    assert generation.scan_approaching_deadlines() == 1
    assert "فات" in Notification.objects.get(recipient=lawyer).body


def test_far_off_deadline_ignored(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    DeadlineFactory(case=case, due_date=dt.date.today() + dt.timedelta(days=60))
    assert generation.scan_approaching_deadlines() == 0


# ── Contract expiring ─────────────────────────────────────
def test_contract_expiring_notifies_case_team(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    c = ContractFactory(
        case=case,
        status=ContractStatus.ACTIVE,
        end_date=dt.date.today() + dt.timedelta(days=10),
    )
    assert generation.scan_expiring_contracts() == 1
    n = Notification.objects.get(recipient=lawyer)
    assert n.category == NotificationCategory.CONTRACT_EXPIRING
    assert n.entity_id == str(c.pk)


def test_draft_contract_not_notified(role_user):
    lawyer = role_user("lawyer")
    case = CaseFactory(assigned_lawyer=lawyer)
    ContractFactory(
        case=case,
        status=ContractStatus.DRAFT,
        end_date=dt.date.today() + dt.timedelta(days=10),
    )
    assert generation.scan_expiring_contracts() == 0


# ── Invoice overdue — the finance side-channel guard ───────
def _overdue_invoice(actor):
    inv = issued_invoice(actor=actor)
    Invoice.objects.filter(pk=inv.pk).update(due_date=dt.date.today() - dt.timedelta(days=5))
    return Invoice.objects.get(pk=inv.pk)


def test_invoice_overdue_reaches_finance_users_only(role_user):
    om = role_user("office_manager")
    fc = role_user("finance_clerk")
    lawyer = role_user("lawyer")  # has finance.view but is NOT finance-responsible
    paralegal = role_user("paralegal")  # NO finance access at all

    inv = _overdue_invoice(om)
    generation.scan_overdue_invoices()

    assert Notification.objects.filter(recipient=om, category="invoice_overdue").exists()
    assert Notification.objects.filter(recipient=fc, category="invoice_overdue").exists()
    # lawyer is not on the finance-responsible recipient list
    assert not Notification.objects.filter(recipient=lawyer, category="invoice_overdue").exists()
    # paralegal must never receive a finance notification
    assert Notification.objects.filter(recipient=paralegal).count() == 0

    body = Notification.objects.filter(category="invoice_overdue").first().body
    assert inv.invoice_number in body
    # no monetary figure is leaked into the body
    assert str(inv.total) not in body
    assert "outstanding" not in body.lower()


def test_paralegal_gets_zero_finance_notifications_from_generate_all(role_user):
    om = role_user("office_manager")
    paralegal = role_user("paralegal")
    _overdue_invoice(om)

    generation.generate_all()

    assert not Notification.objects.filter(recipient=paralegal, category="invoice_overdue").exists()


def test_invoice_scan_idempotent(role_user):
    om = role_user("office_manager")
    _overdue_invoice(om)
    assert generation.scan_overdue_invoices() >= 1
    before = Notification.objects.count()
    assert generation.scan_overdue_invoices() == 0
    assert Notification.objects.count() == before


# ── generate_all ──────────────────────────────────────────
def test_generate_all_runs_every_scan(role_user):
    result = generation.generate_all()
    assert set(result) == {
        "hearing_upcoming",
        "task_overdue",
        "deadline_approaching",
        "invoice_overdue",
        "contract_expiring",
    }
