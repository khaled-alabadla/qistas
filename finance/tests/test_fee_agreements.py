from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.models import CaseEventType
from cases.tests.factories import CaseFactory
from finance import services
from finance.models import FeeAgreement, FeeAgreementStatus, FeeType
from finance.tests.factories import FeeAgreementFactory

pytestmark = pytest.mark.django_db


def test_create_allocates_reference_and_audits_metadata_only(finance_clerk):
    case = CaseFactory()
    fa = services.create_fee_agreement(
        actor=finance_clerk,
        data={
            "case": case,
            "fee_type": FeeType.FIXED,
            "fixed_amount": Decimal("15000"),
            "currency": "ILS",
            "description": "سري لا يُدرَج",
        },
    )
    assert fa.reference.startswith("FA-")
    assert fa.status == FeeAgreementStatus.DRAFT
    assert fa.created_by == finance_clerk
    assert case.events.filter(event_type=CaseEventType.FEE_AGREEMENT_ADDED).exists()
    log = AuditLog.objects.get(action=AuditAction.FEE_AGREEMENT_CREATED, entity_id=str(fa.pk))
    assert "سري لا يُدرَج" not in str(log.changes)
    assert set(log.changes) >= {"reference", "fee_type", "status"}


def test_status_transitions_guarded_and_cancel_terminal(finance_clerk):
    fa = FeeAgreementFactory(status=FeeAgreementStatus.DRAFT)
    services.change_fee_agreement_status(
        actor=finance_clerk, fee_agreement=fa, new_status=FeeAgreementStatus.ACTIVE
    )
    fa.refresh_from_db()
    assert fa.status == FeeAgreementStatus.ACTIVE
    services.change_fee_agreement_status(
        actor=finance_clerk, fee_agreement=fa, new_status=FeeAgreementStatus.CANCELLED
    )
    fa.refresh_from_db()
    with pytest.raises(ValidationError):
        services.change_fee_agreement_status(
            actor=finance_clerk, fee_agreement=fa, new_status=FeeAgreementStatus.ACTIVE
        )


def test_cannot_edit_cancelled_agreement(finance_clerk):
    fa = FeeAgreementFactory(status=FeeAgreementStatus.CANCELLED)
    with pytest.raises(ValidationError):
        services.update_fee_agreement(
            actor=finance_clerk, fee_agreement=fa, data={"fixed_amount": Decimal("1")}
        )


def test_update_diffs_and_audits(finance_clerk):
    fa = FeeAgreementFactory(fixed_amount=Decimal("10000"))
    services.update_fee_agreement(
        actor=finance_clerk, fee_agreement=fa, data={"fixed_amount": Decimal("12000")}
    )
    fa.refresh_from_db()
    assert fa.fixed_amount == Decimal("12000")
    assert AuditLog.objects.filter(action=AuditAction.FEE_AGREEMENT_UPDATED).exists()


# ── views ──────────────────────────────────────────────────
def test_list_and_detail_render(client, finance_clerk):
    fa = FeeAgreementFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("finance:fee_agreement_list")).status_code == 200
    assert client.get(reverse("finance:fee_agreement_detail", args=[fa.pk])).status_code == 200


def test_create_view_by_finance_clerk(client, finance_clerk):
    case = CaseFactory()
    client.force_login(finance_clerk)
    resp = client.post(
        reverse("finance:fee_agreement_create"),
        {"case": case.pk, "fee_type": "fixed", "fixed_amount": "9000", "currency": "ILS"},
    )
    assert resp.status_code == 302
    assert FeeAgreement.objects.count() == 1


def test_create_view_forbidden_for_lawyer(client, lawyer):
    client.force_login(lawyer)
    assert client.get(reverse("finance:fee_agreement_create")).status_code == 403


def test_detail_404_for_missing(client, finance_clerk):
    client.force_login(finance_clerk)
    assert client.get(reverse("finance:fee_agreement_detail", args=[999999])).status_code == 404
