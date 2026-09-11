"""
Phase 13 — release-readiness edge cases (spec Phase 13 §16) not already
covered by a phase's own test suite: malformed URL ids, double-submission,
and a notification whose target becomes inaccessible after generation.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from cases.tests.factories import CaseFactory
from clients.models import ClientStatus
from clients.tests.factories import ClientFactory
from finance import services as fin_services

pytestmark = pytest.mark.django_db


# ── Malformed URL id: the <int:pk> converter itself 404s, never a 500 ──
@pytest.mark.parametrize(
    "path_template",
    [
        "/clients/{}/",
        "/cases/{}/",
        "/hearings/{}/",
        "/tasks/{}/",
        "/documents/{}/download/",
        "/contracts/{}/",
        "/notifications/{}/open/",
    ],
)
def test_malformed_pk_404s_not_500(client, office_manager, path_template):
    """A non-numeric id doesn't even match the `<int:pk>` route — Django's
    resolver 404s before the view (and therefore before any authorization or
    ORM code) ever runs."""
    client.force_login(office_manager)
    assert client.get(path_template.format("abc")).status_code == 404
    assert client.get(path_template.format("1;drop table")).status_code == 404


def test_negative_and_huge_pk_404_not_500(client, office_manager):
    client.force_login(office_manager)
    for path in ("/clients/-1/", "/clients/0/", "/clients/999999999/", "/cases/999999999/"):
        assert client.get(path).status_code == 404


# ── Double submission ────────────────────────────────────────
def test_double_submit_issue_invoice_does_not_double_issue(client, office_manager):
    case = CaseFactory()
    invoice = fin_services.create_invoice(
        actor=office_manager,
        data={
            "client": case.client,
            "case": case,
            "due_date": dt.date.today() + dt.timedelta(days=30),
            "currency": "ILS",
        },
    )
    fin_services.add_line_item(
        actor=office_manager,
        invoice=invoice,
        data={"description": "أتعاب", "quantity": Decimal("1"), "unit_price": Decimal("500")},
    )
    client.force_login(office_manager)
    url = reverse("finance:invoice_issue", args=[invoice.pk])

    first = client.post(url, {})
    second = client.post(url, {})  # simulates a double-click / resubmitted form
    assert first.status_code == 302
    assert second.status_code == 302  # bounced back with an error message, not a 500

    invoice.refresh_from_db()
    from finance.models import Invoice, InvoiceStatus

    assert invoice.status == InvoiceStatus.UNPAID
    assert Invoice.objects.filter(invoice_number=invoice.invoice_number).count() == 1


def test_double_archive_client_is_idempotent(office_manager):
    from audit.models import AuditAction, AuditLog
    from clients import services as client_services

    c = ClientFactory(status=ClientStatus.ACTIVE)
    client_services.archive_client(actor=office_manager, client=c)
    client_services.archive_client(actor=office_manager, client=c)  # second click
    c.refresh_from_db()
    assert c.status == ClientStatus.ARCHIVED
    assert (
        AuditLog.objects.filter(entity_id=str(c.pk), action=AuditAction.CLIENT_ARCHIVED).count()
        == 1
    )


def test_double_mark_all_notifications_read(client, office_manager):
    from notifications.tests.factories import NotificationFactory

    NotificationFactory(recipient=office_manager)
    client.force_login(office_manager)
    url = reverse("notifications:mark_all_read")
    assert client.post(url).status_code == 302
    assert client.post(url).status_code == 302  # nothing left unread -> still a clean no-op


# ── A notification's target becomes inaccessible after generation ──────
def test_notification_target_still_enforces_auth_after_recipient_loses_access(
    client, role_user, office_manager
):
    """A recipient who legitimately received an invoice_overdue notification
    (was finance-responsible at generation time) but is later removed from
    every finance-capable group must still be blocked by the target view —
    the notification itself grants no standing access."""
    from finance.models import Invoice
    from finance.tests.factories import issued_invoice
    from notifications import generation
    from notifications.models import Notification

    fc = role_user("finance_clerk")
    inv = issued_invoice(actor=office_manager)
    Invoice.objects.filter(pk=inv.pk).update(due_date=dt.date.today() - dt.timedelta(days=3))
    generation.scan_overdue_invoices()
    n = Notification.objects.get(recipient=fc, category="invoice_overdue")

    # the finance clerk is reassigned to a non-finance role (e.g. paralegal) —
    # they keep notifications.view but lose finance.view
    from django.contrib.auth.models import Group as AuthGroup

    from core.permissions.capabilities import Group

    fc.groups.set([AuthGroup.objects.get(name=Group.PARALEGAL)])

    client.force_login(fc)
    resp = client.get(reverse("notifications:open", args=[n.pk]))
    # the notification is still theirs to open (it's their own row)...
    assert resp.status_code == 302
    # ...but the finance target it redirects to now correctly denies them.
    target = client.get(resp["Location"])
    assert target.status_code == 403
