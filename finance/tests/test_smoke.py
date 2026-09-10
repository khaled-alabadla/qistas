"""End-to-end HTTP smoke for the Phase 8 surface (finance)."""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from cases.tests.factories import CaseFactory
from finance.tests.factories import ExpenseFactory, FeeAgreementFactory, issued_invoice

pytestmark = pytest.mark.django_db


def test_phase8_pages_render(client, finance_clerk):
    client.force_login(finance_clerk)
    case = CaseFactory()
    inv = issued_invoice(
        actor=finance_clerk, client=case.client, case=case, lines=[("x", 1, "1000")]
    )
    from finance import services

    pay = services.record_payment(
        actor=finance_clerk,
        invoice_id=inv.pk,
        data={"amount": inv.total / 2, "paid_on": dt.date.today(), "method": "cash"},
    )
    fa = FeeAgreementFactory(case=case)
    exp = ExpenseFactory(case=case, client=case.client)

    urls = [
        reverse("finance:invoice_list"),
        reverse("finance:invoice_list") + "?status=unpaid&overdue=on",
        reverse("finance:invoice_create"),
        reverse("finance:invoice_detail", args=[inv.pk]),
        reverse("finance:payment_list"),
        reverse("finance:payment_detail", args=[pay.pk]),
        reverse("finance:fee_agreement_list"),
        reverse("finance:fee_agreement_detail", args=[fa.pk]),
        reverse("finance:fee_agreement_create"),
        reverse("finance:expense_list"),
        reverse("finance:expense_detail", args=[exp.pk]),
        reverse("finance:expense_create"),
        reverse("cases:detail", args=[case.pk]) + "?tab=finance",
        reverse("clients:detail", args=[case.client_id]),
        reverse("core:landing"),
        reverse("agenda:month"),
    ]
    for url in urls:
        assert client.get(url).status_code == 200, url


def test_seed_demo_finance_runs(finance_clerk):
    CaseFactory.create_batch(3)
    call_command("seed_demo_finance", verbosity=0)
    from finance.models import Invoice

    assert Invoice.objects.exists()
