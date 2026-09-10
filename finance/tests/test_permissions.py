import pytest
from django.core.management import call_command
from django.urls import reverse

from core.permissions.capabilities import Capability, can
from finance.tests.factories import ExpenseFactory, FeeAgreementFactory, issued_invoice

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,view,manage",
    [
        ("office_manager", True, True),
        ("finance_clerk", True, True),
        ("lawyer", True, False),
        ("admin_clerk", True, False),
        ("paralegal", False, False),  # NO finance access (spec §12)
    ],
)
def test_capability_matrix(role_user, role, view, manage):
    u = role_user(role)
    assert can(u, Capability.FINANCE_VIEW) is view
    assert can(u, Capability.FINANCE_MANAGE) is manage


_LIST_URLS = [
    "finance:invoice_list",
    "finance:payment_list",
    "finance:expense_list",
    "finance:fee_agreement_list",
]


def test_paralegal_cannot_reach_any_finance_page(client, paralegal, finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    client.force_login(paralegal)
    for name in _LIST_URLS:
        assert client.get(reverse(name)).status_code == 403
    assert client.get(reverse("finance:invoice_detail", args=[inv.pk])).status_code == 403


def test_lawyer_can_view_but_not_mutate(client, lawyer, finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    fa = FeeAgreementFactory()
    exp = ExpenseFactory()
    client.force_login(lawyer)
    # view — OK
    for name in _LIST_URLS:
        assert client.get(reverse(name)).status_code == 200
    assert client.get(reverse("finance:invoice_detail", args=[inv.pk])).status_code == 200
    # mutate — 403
    assert client.get(reverse("finance:invoice_create")).status_code == 403
    assert client.get(reverse("finance:fee_agreement_update", args=[fa.pk])).status_code == 403
    assert client.get(reverse("finance:expense_update", args=[exp.pk])).status_code == 403
    assert client.post(reverse("finance:invoice_issue", args=[inv.pk])).status_code == 403
    assert (
        client.post(
            reverse("finance:payment_create", args=[inv.pk]),
            {"amount": "1", "paid_on": "2026-09-10", "method": "cash"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("finance:credit_note_create", args=[inv.pk]),
            {"amount": "1", "issued_on": "2026-09-10", "reason": "x"},
        ).status_code
        == 403
    )


def test_anonymous_redirected_to_login(client):
    resp = client.get(reverse("finance:invoice_list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_finance_mutations_are_post_only(client, finance_clerk):
    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    client.force_login(finance_clerk)
    for name in (
        "finance:invoice_issue",
        "finance:invoice_cancel",
        "finance:payment_create",
        "finance:credit_note_create",
    ):
        assert client.get(reverse(name, args=[inv.pk])).status_code == 405


def test_invoice_create_prefill_ignores_out_of_scope_ids(client, finance_clerk):
    client.force_login(finance_clerk)
    form = client.get(reverse("finance:invoice_create") + "?client=999999&case=abc").context["form"]
    assert form.initial.get("client") is None


def test_expense_mass_assignment_ignores_reference(client, finance_clerk):
    client.force_login(finance_clerk)
    client.post(
        reverse("finance:expense_create"),
        {
            "description": "x",
            "amount": "10",
            "currency": "ILS",
            "category": "other",
            "spent_on": "2026-09-01",
            "reference": "EXP-1900-0001",
        },
    )
    from finance.models import Expense

    assert Expense.objects.get().reference != "EXP-1900-0001"


def test_sync_roles_idempotent_after_migrate(synced_roles):
    call_command("sync_roles", "--check", verbosity=0)


def test_agenda_calendar_excludes_finance_for_non_viewer(paralegal, finance_clerk):
    """Finance is not all-staff; the all-staff agenda must not leak invoice events."""
    import datetime as dt

    from django.utils import timezone

    from agenda.selectors import calendar_events

    inv = issued_invoice(actor=finance_clerk, lines=[("x", 1, "100")])
    inv.due_date = dt.date.today() + dt.timedelta(days=3)
    inv.save(update_fields=["due_date"])

    start = timezone.make_aware(dt.datetime.combine(dt.date.today(), dt.time.min))
    end = start + dt.timedelta(days=10)
    kinds_para = {e["kind"] for e in calendar_events(paralegal, start, end)}
    kinds_clerk = {e["kind"] for e in calendar_events(finance_clerk, start, end)}
    assert "invoice" not in kinds_para
    assert "invoice" in kinds_clerk
