"""
Phase 13 — end-to-end integration workflows (spec Phase 13 §4).

Qistas is one product, not twelve isolated phase implementations. Each test
here walks a *realistic* multi-step journey across module boundaries —
client → case → hearing/task/document/contract/finance → notification →
dashboard/report/audit — and asserts on the state each step actually leaves
behind, not just "no exception was raised". Where a step is authorization-
sensitive, the workflow also checks the role boundary in place (paralegal has
no finance access; a notification's target still enforces its own auth).

These are workflow-level tests. Per-URL authorization matrices already live
in each app's own `test_permissions.py`/`test_views.py` and in
`tests/test_capability_boundary_sweep.py` (Phase 12) — not duplicated here.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from cases import services as case_services
from cases.models import CaseEventType, CaseStatus, NoteKind, PartyRole
from cases.tests.factories import CaseFactory, CaseTypeFactory
from clients import services as client_services
from clients.models import ClientStatus
from clients.tests.factories import ClientFactory
from courts.tests.factories import CourtFactory
from documents import services as doc_services
from finance import services as fin_services
from finance.models import InvoiceStatus
from hearings import services as hearing_services
from hearings.models import HearingStatus, HearingType
from tasks import services as task_services
from tasks.models import DeadlineStatus, TaskStatus

pytestmark = pytest.mark.django_db


# ── A. Client workflow ──────────────────────────────────────
def test_client_workflow_create_edit_archive_restore(office_manager):
    from audit.models import AuditAction, AuditLog
    from clients.models import Client

    c = client_services.create_client(
        actor=office_manager,
        data={
            "type": "individual",
            "full_name": "أحمد الوفاق",
            "phone": "0599000000",
            "status": ClientStatus.ACTIVE,
        },
    )
    assert c.client_number.startswith("CL-")
    assert AuditLog.objects.filter(entity_id=str(c.pk), action=AuditAction.CLIENT_CREATED).exists()

    client_services.update_client(
        actor=office_manager, client=c, data={"type": "individual", "city": "نابلس"}
    )
    c.refresh_from_db()
    assert c.city == "نابلس"
    assert AuditLog.objects.filter(entity_id=str(c.pk), action=AuditAction.CLIENT_UPDATED).exists()

    client_services.archive_client(actor=office_manager, client=c)
    c.refresh_from_db()
    assert c.status == ClientStatus.ARCHIVED
    assert AuditLog.objects.filter(entity_id=str(c.pk), action=AuditAction.CLIENT_ARCHIVED).exists()
    # archived clients are excluded from the default (active) list
    assert c.pk not in Client.objects.for_user(office_manager).active().values_list("pk", flat=True)

    client_services.restore_client(actor=office_manager, client=c)
    c.refresh_from_db()
    assert c.status == ClientStatus.ACTIVE
    assert AuditLog.objects.filter(entity_id=str(c.pk), action=AuditAction.CLIENT_RESTORED).exists()


# ── B. Case workflow ─────────────────────────────────────────
def test_case_workflow_full_setup_and_visibility(office_manager, lawyer, paralegal):
    from cases.models import Case
    from cases.selectors import case_list

    client_obj = ClientFactory()
    case_type = CaseTypeFactory()
    court = CourtFactory()

    case = case_services.create_case(
        actor=office_manager,
        data={
            "title": "نزاع تجاري",
            "type": case_type,
            "client": client_obj,
            "status": CaseStatus.NEW,
        },
    )
    assert case.case_number.startswith("CS-")

    case_services.update_case(
        actor=office_manager,
        case=case,
        data={
            "title": case.title,
            "type": case_type,
            "client": client_obj,
            "assigned_lawyer": lawyer,
            "court": court,
        },
    )
    case.refresh_from_db()
    assert case.assigned_lawyer_id == lawyer.pk
    assert case.court_id == court.pk

    from core.tests.factories import UserFactory

    supporting = UserFactory()
    added = case_services.add_supporting_lawyer(actor=office_manager, case=case, lawyer=supporting)
    assert added is True
    assert supporting in case.supporting_lawyers.all()

    party = case_services.add_party(
        actor=office_manager,
        case=case,
        data={"party_role": PartyRole.OPPONENT, "name": "شركة النزاع المحدودة"},
    )
    assert party.case_id == case.pk

    note = case_services.add_note(
        actor=office_manager, case=case, body="اجتماع أولي مع الموكل", kind=NoteKind.GENERAL
    )
    assert note.case_id == case.pk

    case_services.change_status(actor=office_manager, case=case, new_status=CaseStatus.IN_PROGRESS)
    case.refresh_from_db()
    assert case.status == CaseStatus.IN_PROGRESS

    # Timeline recorded every meaningful step, oldest first is fine — just
    # assert the expected event types all appear (case-workspace الخط الزمني).
    event_types = set(case.events.values_list("event_type", flat=True))
    assert {
        CaseEventType.CREATED,
        CaseEventType.LAWYER_ASSIGNED,
        CaseEventType.PARTY_ADDED,
        CaseEventType.NOTE_ADDED,
        CaseEventType.STATUS_CHANGED,
    } <= event_types

    # Cases are all-staff visible (ADR-0008) — every role sees it in the list
    # and can open the detail page; write actions are capability-gated
    # (already exhaustively covered elsewhere) — here we only confirm the
    # read-visibility contract integration relies on.
    for user in (office_manager, lawyer, paralegal):
        assert case.pk in case_list(user=user).values_list("pk", flat=True)
        assert Case.objects.for_user(user).filter(pk=case.pk).exists()


# ── C. Hearing workflow ──────────────────────────────────────
def test_hearing_workflow_schedule_agenda_cancel(office_manager, lawyer):
    from agenda.selectors import calendar_events

    case = CaseFactory(assigned_lawyer=lawyer)
    scheduled_at = timezone.now() + dt.timedelta(days=3)
    hearing = hearing_services.schedule_hearing(
        actor=office_manager,
        case=case,
        scheduled_at=scheduled_at,
        hearing_type=HearingType.FIRST_SESSION,
    )
    assert hearing.status == HearingStatus.SCHEDULED

    start = timezone.now()
    events = calendar_events(office_manager, start, start + dt.timedelta(days=7))
    assert any(e["kind"] == "hearing" and e["url"].endswith(f"/{hearing.pk}/") for e in events)

    from hearings.selectors import upcoming_hearings

    assert hearing in list(upcoming_hearings(office_manager, days=7))

    hearing_services.cancel_hearing(
        actor=office_manager, hearing=hearing, reason="تأجيل بطلب الموكل"
    )
    hearing.refresh_from_db()
    assert hearing.status == HearingStatus.CANCELLED
    assert hearing.notes == "تأجيل بطلب الموكل"  # the cancellation reason is recorded

    # cancelled hearings drop out of both the agenda and the upcoming list
    events_after = calendar_events(office_manager, start, start + dt.timedelta(days=7))
    assert not any(e["url"].endswith(f"/{hearing.pk}/") for e in events_after)
    assert hearing not in list(upcoming_hearings(office_manager, days=7))

    # the case timeline records both the scheduling and the cancellation
    event_types = set(case.events.values_list("event_type", flat=True))
    assert CaseEventType.HEARING_SCHEDULED in event_types
    assert CaseEventType.HEARING_CANCELLED in event_types


# ── D. Task / deadline workflow ──────────────────────────────
def test_task_workflow_overdue_and_notification(office_manager, lawyer):
    from notifications import generation
    from notifications.models import Notification
    from tasks.selectors import overdue_tasks

    case = CaseFactory(assigned_lawyer=lawyer)
    task = task_services.create_task(
        actor=office_manager,
        data={
            "title": "تحضير مذكرة الرد",
            "assigned_to": lawyer,
            "case": case,
            "due_date": dt.date.today() - dt.timedelta(days=1),
        },
    )
    assert task.status == TaskStatus.NEW
    assert task.is_overdue is True
    assert task in list(overdue_tasks(office_manager))

    created = generation.scan_overdue_tasks()
    assert created == 1
    n = Notification.objects.get(recipient=lawyer, category="task_overdue")
    assert n.entity_id == str(task.pk)

    task_services.change_task_status(actor=lawyer, task=task, new_status=TaskStatus.DONE)
    task.refresh_from_db()
    assert task.is_overdue is False  # done tasks are never "overdue" (ADR-0006)
    assert task not in list(overdue_tasks(office_manager))


def test_deadline_workflow_approaching_notification_and_completion(office_manager, lawyer):
    from notifications import generation
    from notifications.models import Notification

    case = CaseFactory(assigned_lawyer=lawyer)
    deadline = task_services.create_deadline(
        actor=office_manager,
        data={
            "title": "الموعد النهائي للاستئناف",
            "case": case,
            "due_date": dt.date.today() + dt.timedelta(days=3),
        },
    )
    assert deadline.status == DeadlineStatus.PENDING

    created = generation.scan_approaching_deadlines()
    assert created == 1
    assert Notification.objects.filter(
        recipient=lawyer, category="deadline_approaching", entity_id=str(deadline.pk)
    ).exists()

    task_services.change_deadline_status(
        actor=lawyer, deadline=deadline, new_status=DeadlineStatus.MET
    )
    deadline.refresh_from_db()
    assert deadline.status == DeadlineStatus.MET
    assert deadline.is_overdue is False


# ── E. Document workflow ──────────────────────────────────────
def test_document_workflow_upload_download_authorization(client, office_manager, paralegal):
    from documents.models import Document
    from documents.selectors import case_documents

    case = CaseFactory()
    pdf = SimpleUploadedFile(
        "brief.pdf", b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    )
    doc = doc_services.create_document(
        actor=office_manager,
        uploaded_file=pdf,
        data={"name": "لائحة الدعوى", "case": case},
    )
    assert doc.uploaded_by_id == office_manager.pk
    assert doc in list(case_documents(case))
    assert CaseEventType.DOCUMENT_ADDED in set(case.events.values_list("event_type", flat=True))

    # authorized download
    client.force_login(office_manager)
    resp = client.get(reverse("documents:download", args=[doc.pk]))
    assert resp.status_code == 200
    from audit.models import AuditAction, AuditLog

    assert AuditLog.objects.filter(
        entity_id=str(doc.pk), action=AuditAction.DOCUMENT_DOWNLOADED
    ).exists()

    # a retired document 404s on download, even for an authorized user
    doc_services.retire_document(actor=office_manager, document=doc)
    resp = client.get(reverse("documents:download", args=[doc.pk]))
    assert resp.status_code == 404

    # an unauthenticated user never reaches the file either
    client.logout()
    resp = client.get(reverse("documents:download", args=[doc.pk]))
    assert resp.status_code == 302  # -> login
    assert Document.objects.filter(pk=doc.pk).exists()  # retire is soft-delete, not gone


# ── F. Contract workflow ──────────────────────────────────────
def test_contract_workflow_number_status_expiry_and_paralegal_view_only(
    client, office_manager, paralegal
):
    from contracts.models import ContractStatus
    from contracts.selectors import expiring_contracts

    case = CaseFactory()
    from contracts import services as contract_services

    contract = contract_services.create_contract(
        actor=office_manager,
        data={
            "title": "اتفاقية تمثيل",
            "contract_type": "engagement",
            "client": case.client,
            "case": case,
            "start_date": dt.date.today(),
            "end_date": dt.date.today() + dt.timedelta(days=10),
        },
    )
    assert contract.contract_number.startswith("CT-")
    assert contract.status == ContractStatus.DRAFT

    contract_services.change_contract_status(
        actor=office_manager, contract=contract, new_status=ContractStatus.ACTIVE
    )
    contract.refresh_from_db()
    assert contract.status == ContractStatus.ACTIVE
    assert contract in list(expiring_contracts(office_manager, days=30))

    contract_services.expire_due_contracts(today=dt.date.today() + dt.timedelta(days=11))
    contract.refresh_from_db()
    assert contract.status == ContractStatus.EXPIRED

    # paralegal: view-only (contracts.view yes, contracts.manage no — ADR-0031)
    client.force_login(paralegal)
    assert client.get(reverse("contracts:detail", args=[contract.pk])).status_code == 200
    assert client.get(reverse("contracts:create")).status_code == 403
    status_url = reverse("contracts:status", args=[contract.pk])
    assert client.post(status_url, {"status": "draft"}).status_code == 403


# ── G. Finance workflow ────────────────────────────────────────
def test_finance_workflow_invoice_payment_expense_and_isolation(client, office_manager, paralegal):
    from finance.tests.factories import ExpenseFactory, FeeAgreementFactory

    case = CaseFactory()
    fa = FeeAgreementFactory(case=case)

    due_date = dt.date.today() + dt.timedelta(days=30)
    invoice = fin_services.create_invoice(
        actor=office_manager,
        data={
            "client": case.client,
            "case": case,
            "fee_agreement": fa,
            "due_date": due_date,
            "currency": "ILS",
        },
    )
    fin_services.add_line_item(
        actor=office_manager,
        invoice=invoice,
        data={"description": "أتعاب", "quantity": Decimal("1"), "unit_price": Decimal("2000.00")},
    )
    invoice = fin_services.issue_invoice(actor=office_manager, invoice=invoice)
    assert invoice.status == InvoiceStatus.UNPAID
    assert invoice.invoice_number.startswith("INV-")

    # immutability: no direct field mutation path once issued
    with pytest.raises(ValidationError):
        fin_services.add_line_item(
            actor=office_manager,
            invoice=invoice,
            data={"description": "x", "quantity": Decimal("1"), "unit_price": Decimal("1")},
        )

    fin_services.record_payment(
        actor=office_manager,
        invoice_id=invoice.pk,
        data={"amount": Decimal("500.00"), "paid_on": dt.date.today(), "method": "cash"},
    )
    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID
    assert invoice.amount_paid == Decimal("500.00")
    outstanding = invoice.credited_total - invoice.amount_paid
    assert outstanding == Decimal("1500.00")

    # overpayment is rejected
    with pytest.raises(ValidationError):
        fin_services.record_payment(
            actor=office_manager,
            invoice_id=invoice.pk,
            data={"amount": Decimal("9999.00"), "paid_on": dt.date.today(), "method": "cash"},
        )

    expense = ExpenseFactory(case=case, client=case.client, amount=Decimal("300.00"))

    # expense is money OUT and must never appear in the invoice/fee total
    assert expense.amount not in {invoice.total, invoice.amount_paid, invoice.subtotal}
    invoice.refresh_from_db()
    assert invoice.total == Decimal("2000.00")  # unaffected by the unrelated expense

    from finance.selectors import case_financials

    summary = case_financials(case)
    assert summary  # a real per-case financial breakdown was produced

    # dashboard / report totals: a finance-capable user sees the invoice
    client.force_login(office_manager)
    resp = client.get(reverse("core:landing"))
    assert resp.context["show_finance"] is True

    csv_resp = client.get(reverse("reports:detail", args=["outstanding"]), {"format": "csv"})
    assert csv_resp.status_code == 200
    assert invoice.invoice_number in csv_resp.content.decode("utf-8-sig")

    # paralegal has NO finance access anywhere in this workflow's surface
    client.force_login(paralegal)
    assert client.get(reverse("finance:invoice_detail", args=[invoice.pk])).status_code == 403
    assert client.get(reverse("cases:detail", args=[case.pk]) + "?tab=finance").status_code == 200
    landing = client.get(reverse("core:landing"))
    assert landing.context["show_finance"] is False
    assert invoice.invoice_number not in landing.content.decode()


# ── H. Notification workflow ────────────────────────────────
def test_notification_workflow_generate_dedupe_read_and_target_auth(
    client, office_manager, lawyer, paralegal
):
    from notifications import generation
    from notifications.models import Notification

    case = CaseFactory(assigned_lawyer=lawyer)
    hearing_services.schedule_hearing(
        actor=office_manager,
        case=case,
        scheduled_at=timezone.now() + dt.timedelta(days=1),
        hearing_type=HearingType.FIRST_SESSION,
    )

    created_first = generation.scan_upcoming_hearings()
    created_again = generation.scan_upcoming_hearings()
    assert created_first == 1
    assert created_again == 0  # idempotent — no duplicate on rerun

    n = Notification.objects.get(recipient=lawyer, category="hearing_upcoming")
    assert n.read_at is None

    # the lawyer can open it — marks read, redirects to the hearing detail,
    # and that target view still enforces its own authorization
    client.force_login(lawyer)
    resp = client.get(reverse("notifications:open", args=[n.pk]))
    assert resp.status_code == 302
    n.refresh_from_db()
    assert n.read_at is not None

    # a different user (paralegal) cannot open or mark someone else's notification
    client.force_login(paralegal)
    assert client.get(reverse("notifications:open", args=[n.pk])).status_code == 404
    assert (
        client.post(reverse("notifications:mark_read", args=[n.pk])).status_code == 302
    )  # scoped no-op, not an error
    n.refresh_from_db()
    assert n.read_at is not None  # unchanged from the lawyer's own read


# ── I. Reporting workflow ───────────────────────────────────
def test_reporting_workflow_scoping_totals_and_currency(client, office_manager, paralegal):
    case_ils = CaseFactory()
    case_usd = CaseFactory()
    due_date = dt.date.today() + dt.timedelta(days=30)
    ils_invoice = fin_services.create_invoice(
        actor=office_manager,
        data={"client": case_ils.client, "case": case_ils, "due_date": due_date, "currency": "ILS"},
    )
    fin_services.add_line_item(
        actor=office_manager,
        invoice=ils_invoice,
        data={"description": "أتعاب", "quantity": Decimal("1"), "unit_price": Decimal("1000.00")},
    )
    fin_services.issue_invoice(actor=office_manager, invoice=ils_invoice)

    usd_invoice = fin_services.create_invoice(
        actor=office_manager,
        data={"client": case_usd.client, "case": case_usd, "due_date": due_date, "currency": "USD"},
    )
    fin_services.add_line_item(
        actor=office_manager,
        invoice=usd_invoice,
        data={"description": "Fees", "quantity": Decimal("1"), "unit_price": Decimal("500.00")},
    )
    fin_services.issue_invoice(actor=office_manager, invoice=usd_invoice)

    client.force_login(office_manager)
    resp = client.get(reverse("reports:detail", args=["revenue"]))
    assert resp.status_code == 200
    body = resp.content.decode()
    # currencies are never summed into one combined figure (ADR-0032/0034)
    assert "1500" not in body.replace(",", "")

    # scoping: a paralegal can run the (non-financial) cases report...
    client.force_login(paralegal)
    cases_resp = client.get(reverse("reports:detail", args=["cases"]))
    assert cases_resp.status_code == 200
    # ...but not the financial one
    assert client.get(reverse("reports:detail", args=["revenue"])).status_code == 403
