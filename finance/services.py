"""
Transactional writes for the finance domain (docs/adr/0011, 0012, 0013, 0018,
0020, 0021, 0032).

Every mutation:
* runs in ``transaction.atomic``;
* does all money arithmetic here (``core.money`` — ``Decimal``, ``quantize``),
  never trusting a browser-supplied total / balance / number;
* writes an ``audit.AuditLog`` event with **metadata only** (references, numbers,
  amounts, status, changed field names — never ``description`` / ``notes`` /
  ``reason`` bodies, ADR-0009);
* records a ``CaseEvent`` on the case timeline for the client-facing milestones
  (fee agreement added, invoice issued, payment recorded, credit note issued)
  when the record is case-linked — draft edits / expenses / reversals are
  audit-only (spec §26).

Immutability (ADR-0012):
* ``update_invoice`` / line-item calls refuse a non-draft invoice;
* ``Payment`` / ``PaymentReversal`` / ``CreditNote`` are create-only;
* the overpayment guard holds a ``select_for_update`` lock on the invoice row
  while it reads the outstanding balance and writes ``amount_paid`` (§40).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from audit.events import log_event
from audit.models import AuditAction
from cases.models import CaseEventType
from cases.services import record_case_event
from core.money import ZERO, quantize
from core.numbering import format_reference, next_number
from finance.models import (
    CreditNote,
    Expense,
    FeeAgreement,
    FeeAgreementStatus,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    Payment,
    PaymentReversal,
)

# ── reference numbers (ADR-0021) ───────────────────────────
_PREFIX = {
    "fee_agreement": "FA",
    "invoice": "INV",
    "payment": "PMT",
    "credit_note": "CN",
    "expense": "EXP",
}


def _allocate(scope: str) -> str:
    period = str(timezone.localdate().year)
    return format_reference(_PREFIX[scope], next_number(scope, period=period), period=period)


# ── FeeAgreement ───────────────────────────────────────────
FEE_AGREEMENT_EDITABLE = (
    "case",
    "fee_type",
    "fixed_amount",
    "hourly_rate",
    "contingency_percent",
    "currency",
    "agreed_on",
    "start_date",
    "end_date",
    "description",
    "notes",
)

_FEE_STATUS_TRANSITIONS = {
    FeeAgreementStatus.DRAFT: {FeeAgreementStatus.ACTIVE, FeeAgreementStatus.CANCELLED},
    FeeAgreementStatus.ACTIVE: {FeeAgreementStatus.COMPLETED, FeeAgreementStatus.CANCELLED},
    FeeAgreementStatus.COMPLETED: {FeeAgreementStatus.ACTIVE},
    FeeAgreementStatus.CANCELLED: set(),
}


def _fee_meta(fa: FeeAgreement) -> dict:
    return {
        "reference": fa.reference,
        "fee_type": fa.fee_type,
        "status": fa.status,
        "fixed_amount": str(fa.fixed_amount) if fa.fixed_amount is not None else None,
        "hourly_rate": str(fa.hourly_rate) if fa.hourly_rate is not None else None,
        "contingency_percent": (
            str(fa.contingency_percent) if fa.contingency_percent is not None else None
        ),
    }


@transaction.atomic
def create_fee_agreement(*, actor, data: dict, request=None) -> FeeAgreement:
    data = {k: v for k, v in data.items() if k in FEE_AGREEMENT_EDITABLE}
    fa = FeeAgreement(**data)
    fa.reference = _allocate("fee_agreement")
    fa.status = FeeAgreementStatus.DRAFT
    fa.created_by = actor
    fa.updated_by = actor
    fa.full_clean(exclude=["reference", "created_by", "updated_by"])
    fa.save()
    if fa.case_id:
        record_case_event(
            fa.case,
            CaseEventType.FEE_AGREEMENT_ADDED,
            f"اتفاقية أتعاب: {fa.reference} ({fa.get_fee_type_display()})",
            actor=actor,
            fee_agreement_id=fa.pk,
        )
    log_event(
        request, AuditAction.FEE_AGREEMENT_CREATED, actor=actor, obj=fa, changes=_fee_meta(fa)
    )
    return fa


@transaction.atomic
def update_fee_agreement(
    *, actor, fee_agreement: FeeAgreement, data: dict, request=None
) -> FeeAgreement:
    if fee_agreement.status in {FeeAgreementStatus.COMPLETED, FeeAgreementStatus.CANCELLED}:
        raise ValidationError(_("لا يمكن تعديل اتفاقية منجزة أو ملغاة."))
    data = {k: v for k, v in data.items() if k in FEE_AGREEMENT_EDITABLE}
    stored = FeeAgreement.objects.get(pk=fee_agreement.pk)
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return fee_agreement
    for field, value in data.items():
        setattr(fee_agreement, field, value)
    fee_agreement.updated_by = actor
    fee_agreement.full_clean(exclude=["reference", "created_by", "updated_by"])
    fee_agreement.save()
    log_event(
        request,
        AuditAction.FEE_AGREEMENT_UPDATED,
        actor=actor,
        obj=fee_agreement,
        changes={"fields": sorted(changed)},
    )
    return fee_agreement


@transaction.atomic
def change_fee_agreement_status(
    *, actor, fee_agreement: FeeAgreement, new_status: str, request=None
) -> FeeAgreement:
    if fee_agreement.status == new_status:
        return fee_agreement
    if new_status not in _FEE_STATUS_TRANSITIONS.get(fee_agreement.status, set()):
        raise ValidationError(_("انتقال حالة غير مسموح."))
    previous = fee_agreement.status
    fee_agreement.status = new_status
    fee_agreement.updated_by = actor
    fee_agreement.save(update_fields=["status", "updated_by", "updated_at"])
    log_event(
        request,
        AuditAction.FEE_AGREEMENT_STATUS_CHANGED,
        actor=actor,
        obj=fee_agreement,
        changes={"status": [previous, new_status]},
    )
    return fee_agreement


# ── Invoice — draft lifecycle + issue + cancel ─────────────
INVOICE_DRAFT_EDITABLE = ("client", "case", "fee_agreement", "due_date", "currency", "notes")
INVOICE_DRAFT_MONEY_INPUTS = ("discount", "tax_rate")


def _invoice_meta(inv: Invoice) -> dict:
    return {
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "subtotal": str(inv.subtotal),
        "discount": str(inv.discount),
        "tax_amount": str(inv.tax_amount),
        "total": str(inv.total),
        "amount_paid": str(inv.amount_paid),
    }


def _require_draft(invoice: Invoice) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError(_("لا يمكن تعديل فاتورة صادرة (تصحّح بإشعار دائن)."))


def recalculate_invoice(invoice: Invoice) -> Invoice:
    """Recompute ``subtotal`` / ``tax_amount`` / ``total`` from the line items +
    the draft inputs. **Draft only** — never touches an issued invoice."""
    _require_draft(invoice)
    subtotal = quantize(invoice.line_items.aggregate(s=Sum("line_total"))["s"] or ZERO)
    discount = quantize(invoice.discount or ZERO)
    # A discount larger than the subtotal only zeroes the bill; it is never
    # stored as a negative. `issue_invoice` rejects `discount > subtotal`.
    taxable = max(subtotal - discount, ZERO)
    tax_amount = quantize(taxable * (invoice.tax_rate or ZERO) / 100)
    invoice.subtotal = subtotal
    invoice.discount = discount
    invoice.tax_amount = tax_amount
    invoice.total = quantize(taxable + tax_amount)
    invoice.save(update_fields=["subtotal", "discount", "tax_amount", "total", "updated_at"])
    return invoice


def _money_inputs(data: dict) -> dict:
    """Draft money inputs from a (bound) form: a **present but blank** field means
    "clear it" → ``ZERO``; an absent key is left untouched."""
    return {
        k: (quantize(data[k]) if data.get(k) is not None else ZERO)
        for k in INVOICE_DRAFT_MONEY_INPUTS
        if k in data
    }


def _check_invoice_links(case, fee_agreement) -> None:
    """A fee agreement belongs to exactly one case — an invoice may not pair it
    with a different case."""
    if fee_agreement is not None and case is not None and fee_agreement.case_id != case.pk:
        raise ValidationError({"fee_agreement": _("اتفاقية الأتعاب تخص قضية أخرى.")})


@transaction.atomic
def create_invoice(*, actor, data: dict, request=None) -> Invoice:
    fields = {k: v for k, v in data.items() if k in INVOICE_DRAFT_EDITABLE}
    _check_invoice_links(fields.get("case"), fields.get("fee_agreement"))
    invoice = Invoice(**fields, **_money_inputs(data))
    invoice.status = InvoiceStatus.DRAFT
    invoice.created_by = actor
    invoice.updated_by = actor
    invoice.full_clean(exclude=["invoice_number", "created_by", "updated_by"])
    invoice.save()
    recalculate_invoice(invoice)
    log_event(
        request,
        AuditAction.INVOICE_CREATED,
        actor=actor,
        obj=invoice,
        changes=_invoice_meta(invoice),
    )
    return invoice


@transaction.atomic
def update_invoice(*, actor, invoice: Invoice, data: dict, request=None) -> Invoice:
    _require_draft(invoice)
    fields = {k: v for k, v in data.items() if k in INVOICE_DRAFT_EDITABLE}
    _check_invoice_links(
        fields.get("case", invoice.case), fields.get("fee_agreement", invoice.fee_agreement)
    )
    stored = Invoice.objects.get(pk=invoice.pk)
    payload = {**fields, **_money_inputs(data)}
    changed = [f for f, v in payload.items() if getattr(stored, f) != v]
    if not changed:
        return invoice
    for field, value in payload.items():
        setattr(invoice, field, value)
    invoice.updated_by = actor
    invoice.full_clean(exclude=["invoice_number", "created_by", "updated_by"])
    invoice.save()
    recalculate_invoice(invoice)
    log_event(
        request,
        AuditAction.INVOICE_UPDATED,
        actor=actor,
        obj=invoice,
        changes={"fields": sorted(changed)},
    )
    return invoice


@transaction.atomic
def add_line_item(*, actor, invoice: Invoice, data: dict, request=None) -> InvoiceLineItem:
    _require_draft(invoice)
    last = invoice.line_items.order_by("-position").first()
    line = InvoiceLineItem(
        invoice=invoice,
        description=data["description"],
        quantity=quantize(data.get("quantity") or 1),
        unit_price=quantize(data["unit_price"]),
        position=(last.position + 1) if last else 0,
    )
    line.line_total = line.compute_total()
    line.full_clean()
    line.save()
    recalculate_invoice(invoice)
    log_event(
        request,
        AuditAction.INVOICE_UPDATED,
        actor=actor,
        obj=invoice,
        changes={"line_added": line.description[:80], "total": str(invoice.total)},
    )
    return line


@transaction.atomic
def remove_line_item(*, actor, invoice: Invoice, line: InvoiceLineItem, request=None) -> Invoice:
    _require_draft(invoice)
    if line.invoice_id != invoice.pk:
        raise ValidationError(_("البند لا يخص هذه الفاتورة."))
    label = line.description[:80]
    line.delete()  # a draft line item — hard delete is correct within the aggregate
    recalculate_invoice(invoice)
    log_event(
        request,
        AuditAction.INVOICE_UPDATED,
        actor=actor,
        obj=invoice,
        changes={"line_removed": label, "total": str(invoice.total)},
    )
    return invoice


@transaction.atomic
def issue_invoice(*, actor, invoice: Invoice, issue_date=None, request=None) -> Invoice:
    # Lock the row and re-check under the lock so a double-submit cannot issue
    # the invoice twice (burning a number, doubling the audit + case events).
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError(_("الفاتورة صادرة بالفعل."))
    if not invoice.line_items.exists():
        raise ValidationError(_("لا يمكن إصدار فاتورة بدون بنود."))
    recalculate_invoice(invoice)
    if invoice.discount > invoice.subtotal:
        raise ValidationError(_("الخصم يتجاوز المجموع الفرعي."))
    if invoice.total <= 0:
        raise ValidationError(_("إجمالي الفاتورة يجب أن يكون أكبر من صفر."))
    invoice.invoice_number = _allocate("invoice")
    invoice.issue_date = issue_date or timezone.localdate()
    invoice.status = InvoiceStatus.UNPAID
    invoice.updated_by = actor
    invoice.save(
        update_fields=["invoice_number", "issue_date", "status", "updated_by", "updated_at"]
    )
    if invoice.case_id:
        record_case_event(
            invoice.case,
            CaseEventType.INVOICE_ISSUED,
            f"صدرت الفاتورة {invoice.invoice_number} بمبلغ {invoice.total} {invoice.currency}",
            actor=actor,
            invoice_id=invoice.pk,
        )
    log_event(
        request,
        AuditAction.INVOICE_ISSUED,
        actor=actor,
        obj=invoice,
        changes=_invoice_meta(invoice),
    )
    return invoice


@transaction.atomic
def cancel_invoice(*, actor, invoice: Invoice, request=None) -> Invoice:
    """Direct cancel is a DRAFT-only path (ADR-0012). An issued invoice is voided
    by a full-value credit note, not here."""
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError(_("تُلغى الفاتورة الصادرة عبر إشعار دائن بكامل القيمة."))
    invoice.status = InvoiceStatus.CANCELLED
    invoice.updated_by = actor
    invoice.save(update_fields=["status", "updated_by", "updated_at"])
    log_event(
        request,
        AuditAction.INVOICE_CANCELLED,
        actor=actor,
        obj=invoice,
        changes=_invoice_meta(invoice),
    )
    return invoice


def _apply_payment_status(invoice: Invoice) -> None:
    """Set the payment-derived status from ``amount_paid`` vs ``credited_total``.
    Caller holds the ``select_for_update`` lock. Never called on draft/cancelled."""
    if invoice.status in {InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED}:
        return
    credited = invoice.credited_total
    if invoice.amount_paid <= 0:
        invoice.status = InvoiceStatus.UNPAID
    elif invoice.amount_paid >= credited:
        invoice.status = InvoiceStatus.PAID
    else:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    invoice.save(update_fields=["status", "updated_at"])


# ── Payment — the overpayment guard (§40) ──────────────────
@transaction.atomic
def record_payment(*, actor, invoice_id: int, data: dict, request=None) -> Payment:
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)  # row lock
    if invoice.status not in {
        InvoiceStatus.UNPAID,
        InvoiceStatus.PARTIALLY_PAID,
    }:
        raise ValidationError(_("لا يمكن تسجيل دفعة على هذه الفاتورة."))

    amount = quantize(data["amount"])
    outstanding = quantize(invoice.credited_total - invoice.amount_paid)
    if amount <= 0:
        raise ValidationError({"amount": _("المبلغ يجب أن يكون أكبر من صفر.")})
    if amount > outstanding:
        raise ValidationError(
            {"amount": _("المبلغ يتجاوز الرصيد المتبقي (%(bal)s).") % {"bal": outstanding}}
        )

    payment = Payment(
        reference=_allocate("payment"),
        invoice=invoice,
        amount=amount,
        paid_on=data.get("paid_on") or timezone.localdate(),
        method=data.get("method") or "cash",
        external_reference=data.get("external_reference", ""),
        note=data.get("note", ""),
        created_by=actor,
        updated_by=actor,
    )
    payment.full_clean(exclude=["reference", "created_by", "updated_by"])
    payment.save()

    invoice.amount_paid = F("amount_paid") + amount
    invoice.save(update_fields=["amount_paid", "updated_at"])
    invoice.refresh_from_db(fields=["amount_paid", "status"])
    _apply_payment_status(invoice)

    if invoice.case_id:
        record_case_event(
            invoice.case,
            CaseEventType.PAYMENT_RECORDED,
            f"دفعة {payment.amount} {invoice.currency} على الفاتورة {invoice.invoice_number}",
            actor=actor,
            payment_id=payment.pk,
        )
    log_event(
        request,
        AuditAction.PAYMENT_RECORDED,
        actor=actor,
        obj=payment,
        changes={
            "reference": payment.reference,
            "invoice_number": invoice.invoice_number,
            "amount": str(payment.amount),
            "method": payment.method,
        },
    )
    return payment


@transaction.atomic
def reverse_payment(*, actor, payment_id: int, data: dict, request=None) -> PaymentReversal:
    payment = Payment.objects.select_related("invoice").get(pk=payment_id)
    invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
    amount = quantize(data["amount"])
    already = payment.reversals.aggregate(s=Sum("amount"))["s"] or ZERO
    if amount <= 0:
        raise ValidationError({"amount": _("المبلغ يجب أن يكون أكبر من صفر.")})
    if quantize(already + amount) > payment.amount:
        raise ValidationError({"amount": _("المبلغ يتجاوز قيمة الدفعة القابلة للاسترجاع.")})

    reversal = PaymentReversal(
        payment=payment,
        amount=amount,
        reason=data["reason"],
        reversed_on=data.get("reversed_on") or timezone.localdate(),
        created_by=actor,
        updated_by=actor,
    )
    reversal.full_clean(exclude=["created_by", "updated_by"])
    reversal.save()

    invoice.amount_paid = F("amount_paid") - amount
    invoice.save(update_fields=["amount_paid", "updated_at"])
    invoice.refresh_from_db(fields=["amount_paid", "status"])
    _apply_payment_status(invoice)

    log_event(
        request,
        AuditAction.PAYMENT_REVERSED,
        actor=actor,
        obj=payment,
        changes={
            "reference": payment.reference,
            "reversed": str(amount),
            "invoice_number": invoice.invoice_number,
        },
    )
    return reversal


# ── CreditNote — correct an issued invoice (ADR-0012) ──────
@transaction.atomic
def issue_credit_note(*, actor, invoice_id: int, data: dict, request=None) -> CreditNote:
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    if invoice.status not in {
        InvoiceStatus.UNPAID,
        InvoiceStatus.PARTIALLY_PAID,
        InvoiceStatus.PAID,
    }:
        raise ValidationError(_("يصدر الإشعار الدائن على فاتورة صادرة فقط."))

    amount = quantize(data["amount"])
    already = invoice.credit_notes.aggregate(s=Sum("amount"))["s"] or ZERO
    if amount <= 0:
        raise ValidationError({"amount": _("المبلغ يجب أن يكون أكبر من صفر.")})
    if quantize(already + amount) > invoice.total:
        raise ValidationError({"amount": _("الإجمالي المُصدَر يتجاوز قيمة الفاتورة.")})

    note = CreditNote(
        credit_number=_allocate("credit_note"),
        invoice=invoice,
        amount=amount,
        reason=data["reason"],
        issued_on=data.get("issued_on") or timezone.localdate(),
        created_by=actor,
        updated_by=actor,
    )
    note.full_clean(exclude=["credit_number", "created_by", "updated_by"])
    note.save()

    # Fully credited → the receivable is void.
    total_credited = quantize(already + amount)
    if total_credited >= invoice.total:
        invoice.status = InvoiceStatus.CANCELLED
        invoice.save(update_fields=["status", "updated_at"])
    else:
        invoice.refresh_from_db(fields=["amount_paid", "status"])
        _apply_payment_status(invoice)

    if invoice.case_id:
        record_case_event(
            invoice.case,
            CaseEventType.CREDIT_NOTE_ISSUED,
            f"إشعار دائن {note.credit_number} بمبلغ {note.amount} "
            f"على الفاتورة {invoice.invoice_number}",
            actor=actor,
            credit_note_id=note.pk,
        )
    log_event(
        request,
        AuditAction.CREDIT_NOTE_ISSUED,
        actor=actor,
        obj=note,
        changes={
            "credit_number": note.credit_number,
            "invoice_number": invoice.invoice_number,
            "amount": str(note.amount),
        },
    )
    return note


# ── Expense ────────────────────────────────────────────────
EXPENSE_EDITABLE = (
    "description",
    "amount",
    "currency",
    "category",
    "spent_on",
    "case",
    "client",
    "note",
)


def _expense_meta(exp: Expense) -> dict:
    return {
        "reference": exp.reference,
        "category": exp.category,
        "amount": str(exp.amount),
        "currency": exp.currency,
    }


@transaction.atomic
def create_expense(*, actor, data: dict, request=None) -> Expense:
    fields = {k: v for k, v in data.items() if k in EXPENSE_EDITABLE}
    if fields.get("amount") is not None:
        fields["amount"] = quantize(fields["amount"])
    exp = Expense(**fields)
    exp.reference = _allocate("expense")
    exp.created_by = actor
    exp.updated_by = actor
    exp.full_clean(exclude=["reference", "created_by", "updated_by"])
    exp.save()
    log_event(
        request, AuditAction.EXPENSE_CREATED, actor=actor, obj=exp, changes=_expense_meta(exp)
    )
    return exp


@transaction.atomic
def update_expense(*, actor, expense: Expense, data: dict, request=None) -> Expense:
    if expense.deleted_at is not None:
        raise ValidationError(_("لا يمكن تعديل مصروف مسحوب."))
    fields = {k: v for k, v in data.items() if k in EXPENSE_EDITABLE}
    if fields.get("amount") is not None:
        fields["amount"] = quantize(fields["amount"])
    stored = Expense.objects.get(pk=expense.pk)
    changed = [f for f, v in fields.items() if getattr(stored, f) != v]
    if not changed:
        return expense
    for field, value in fields.items():
        setattr(expense, field, value)
    expense.updated_by = actor
    expense.full_clean(exclude=["reference", "created_by", "updated_by"])
    expense.save()
    log_event(
        request,
        AuditAction.EXPENSE_UPDATED,
        actor=actor,
        obj=expense,
        changes={"fields": sorted(changed)},
    )
    return expense


@transaction.atomic
def retire_expense(*, actor, expense: Expense, request=None) -> Expense:
    if expense.deleted_at is not None:
        return expense
    expense.deleted_at = timezone.now()
    expense.deleted_by = actor
    expense.save(update_fields=["deleted_at", "deleted_by"])
    log_event(
        request,
        AuditAction.EXPENSE_RETIRED,
        actor=actor,
        obj=expense,
        changes=_expense_meta(expense),
    )
    return expense
