"""Permission-scoped reads for the finance domain (docs/adr/0019, 0028, 0032)."""

from __future__ import annotations

import datetime as dt

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from core.money import ZERO, quantize
from finance.models import (
    Expense,
    ExpenseCategory,
    FeeAgreement,
    FeeAgreementStatus,
    FeeType,
    Invoice,
    InvoiceStatus,
    Payment,
)

_MONEY = DecimalField(max_digits=16, decimal_places=2)
_ZERO_SUM = Value(ZERO, output_field=_MONEY)

_INVOICE_SELECT = ("client", "case", "fee_agreement", "created_by")
_PAYMENT_SELECT = ("invoice", "invoice__client", "created_by")
_FEE_SELECT = ("case", "case__client", "created_by")
_EXPENSE_SELECT = ("case", "client", "created_by")


# ── Fee agreements ─────────────────────────────────────────
def fee_agreement_list(
    *, user, query: str = "", status: str = "", fee_type: str = "", case_id: str = ""
):
    qs = FeeAgreement.objects.for_user(user).select_related(*_FEE_SELECT)
    if query:
        qs = qs.search(query)
    if status in FeeAgreementStatus.values:
        qs = qs.filter(status=status)
    if fee_type in FeeType.values:
        qs = qs.filter(fee_type=fee_type)
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)
    return qs


def case_fee_agreements(case):
    return case.fee_agreements.select_related("created_by").order_by("-created_at")


# ── Invoices ───────────────────────────────────────────────
def invoice_list(
    *,
    user,
    query: str = "",
    status: str = "",
    client_id: str = "",
    case_id: str = "",
    overdue_only: bool = False,
    include_cancelled: bool = False,
):
    qs = Invoice.objects.for_user(user).select_related(*_INVOICE_SELECT).with_balances()
    if query:
        qs = qs.search(query)
    if status in InvoiceStatus.values:
        qs = qs.filter(status=status)
    elif not include_cancelled:
        qs = qs.exclude(status=InvoiceStatus.CANCELLED)
    if str(client_id).isdigit():
        qs = qs.filter(client_id=client_id)
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)
    if overdue_only:
        qs = qs.overdue()
    return qs.order_by("-created_at")


def case_invoices(case):
    return (
        case.invoices.select_related("client", "created_by").with_balances().order_by("-created_at")
    )


def client_invoices(client):
    return (
        client.invoices.select_related("case", "created_by").with_balances().order_by("-created_at")
    )


def invoice_detail_queryset(user):
    """Scoped queryset for the invoice detail view — prefetches everything the
    page renders so it is a fixed number of queries."""
    return (
        Invoice.objects.for_user(user)
        .select_related(*_INVOICE_SELECT)
        .with_balances()
        .prefetch_related("line_items", "payments__reversals", "credit_notes")
    )


# ── Payments ───────────────────────────────────────────────
def payment_list(
    *, user, query: str = "", method: str = "", client_id: str = "", case_id: str = ""
):
    qs = (
        Payment.objects.for_user(user)
        .select_related(*_PAYMENT_SELECT)
        .prefetch_related("reversals")
    )
    q = (query or "").strip()
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(invoice__invoice_number__icontains=q))
    if method:
        qs = qs.filter(method=method)
    if str(client_id).isdigit():
        qs = qs.filter(invoice__client_id=client_id)
    if str(case_id).isdigit():
        qs = qs.filter(invoice__case_id=case_id)
    return qs


def case_payments(case):
    return (
        Payment.objects.filter(invoice__case=case)
        .select_related("invoice", "created_by")
        .prefetch_related("reversals")
        .order_by("-paid_on", "-created_at")
    )


def client_payments(client):
    return (
        Payment.objects.filter(invoice__client=client)
        .select_related("invoice", "created_by")
        .prefetch_related("reversals")
        .order_by("-paid_on", "-created_at")
    )


# ── Expenses ───────────────────────────────────────────────
def expense_list(
    *,
    user,
    query: str = "",
    category: str = "",
    case_id: str = "",
    client_id: str = "",
    include_retired: bool = False,
):
    qs = Expense.objects.for_user(user).select_related(*_EXPENSE_SELECT)
    if not include_retired:
        qs = qs.alive()
    if query:
        qs = qs.search(query)
    if category in ExpenseCategory.values:
        qs = qs.filter(category=category)
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)
    if str(client_id).isdigit():
        qs = qs.filter(client_id=client_id)
    return qs


def case_expenses(case):
    return (
        case.expenses.filter(deleted_at__isnull=True)
        .select_related("created_by")
        .order_by("-spent_on")
    )


# ── Financial summaries (§21, §97, §98) ────────────────────
def _issued(qs):
    return qs.exclude(status__in=[InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED])


def _invoice_totals_by_currency(invoice_qs) -> list[dict]:
    """One row per currency: invoiced (= total), credited (= Σ credit notes),
    paid, outstanding = max(invoiced − credited − paid, 0). Amounts in different
    currencies are **never** summed into one figure (an office may invoice in
    ILS + USD — spec §21's flat 'ملخص مالي' assumes a single currency)."""
    issued = _issued(invoice_qs)
    # Invoice-column sums and the credit-note sum are aggregated in SEPARATE
    # queries: joining `credit_notes` into the first would fan out `total` /
    # `amount_paid` for every credit note on an invoice.
    totals = {
        r["currency"]: r
        for r in issued.values("currency").annotate(
            invoiced=Coalesce(Sum("total"), _ZERO_SUM),
            paid=Coalesce(Sum("amount_paid"), _ZERO_SUM),
        )
    }
    credited = {
        r["currency"]: r["c"]
        for r in issued.values("currency").annotate(
            c=Coalesce(Sum("credit_notes__amount"), _ZERO_SUM)
        )
    }
    out = []
    for currency in sorted(totals):
        invoiced = quantize(totals[currency]["invoiced"])
        paid = quantize(totals[currency]["paid"])
        cr = quantize(credited.get(currency) or ZERO)
        out.append(
            {
                "currency": currency,
                "invoiced": invoiced,
                "paid": paid,
                "credited": cr,
                "outstanding": quantize(max(invoiced - cr - paid, ZERO)),
            }
        )
    return out


def client_financials(client) -> dict:
    """إجمالي الفواتير / المدفوع / المتبقي for the client profile (§21) — a
    per-currency breakdown over **issued** invoices, credit-note aware."""
    by_currency = _invoice_totals_by_currency(client.invoices)
    return {"by_currency": by_currency, "multi_currency": len(by_currency) > 1}


def case_financials(case) -> dict:
    by_currency = _invoice_totals_by_currency(case.invoices)
    expenses = (
        case.expenses.filter(deleted_at__isnull=True)
        .values("currency")
        .annotate(total=Coalesce(Sum("amount"), _ZERO_SUM))
        .order_by("currency")
    )
    return {
        "by_currency": by_currency,
        "expenses_by_currency": [
            {"currency": e["currency"], "total": quantize(e["total"])} for e in expenses
        ],
        "multi_currency": len(by_currency) > 1,
    }


def outstanding_invoices(user, *, limit: int | None = None):
    from django.db.models import F

    qs = (
        Invoice.objects.for_user(user)
        .open()
        .select_related("client", "case")
        .with_balances()
        .order_by(F("due_date").asc(nulls_last=True), "-created_at")
    )
    return qs[:limit] if limit else qs


def overdue_invoices(user, *, limit: int | None = None):
    """Issued, still-open invoices whose ``due_date`` has passed (§19 attention)."""
    from django.db.models import F

    qs = (
        Invoice.objects.for_user(user)
        .overdue()
        .select_related("client", "case")
        .with_balances()
        .order_by(F("due_date").asc(nulls_last=True))
    )
    return qs[:limit] if limit else qs


def firm_financials(user, *, caps: set[str] | None = None) -> dict:
    """Firm-wide per-currency invoiced / paid / outstanding + expenses over
    everything ``user`` may see — powers the dashboard Financial Overview (§19).

    **Capability-aware:** returns empty + ``visible=False`` for a user without
    ``finance.view`` (paralegal), a defence-in-depth backstop on top of the
    view-level gate (Phase 8 rule — finance is not all-staff). ``caps`` (a
    pre-computed capability set) lets ``build_dashboard`` avoid a second
    identical group-membership query."""
    from core.permissions.capabilities import Capability, can

    has_finance = (
        Capability.FINANCE_VIEW in caps if caps is not None else can(user, Capability.FINANCE_VIEW)
    )
    if not has_finance:
        return {
            "visible": False,
            "by_currency": [],
            "expenses_by_currency": [],
            "multi_currency": False,
        }
    by_currency = _invoice_totals_by_currency(Invoice.objects.for_user(user))
    expenses = (
        Expense.objects.for_user(user)
        .alive()
        .values("currency")
        .annotate(total=Coalesce(Sum("amount"), _ZERO_SUM))
        .order_by("currency")
    )
    return {
        "visible": True,
        "by_currency": by_currency,
        "expenses_by_currency": [
            {"currency": e["currency"], "total": quantize(e["total"])} for e in expenses
        ],
        "multi_currency": len(by_currency) > 1,
    }


# ── Calendar (agenda aggregator — docs/adr/0028) ───────────
def _combine(d: dt.date) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(d, dt.time.min), timezone.get_current_timezone())


def _invoice_event(inv: Invoice) -> dict:
    return {
        "start": _combine(inv.due_date),
        "title": f"{inv.invoice_number} — {inv.client.display_name}",
        "kind": "invoice",
        "all_day": True,
        "status": inv.status,
        "done": False,
        "url": reverse("finance:invoice_detail", args=[inv.pk]),
        "meta": {
            "amount": str(inv.outstanding),
            "currency": inv.currency,
            "overdue": inv.is_overdue,
            "case_title": inv.case.title if inv.case_id else "",
        },
    }


def calendar_items(user, start, end) -> list[dict]:
    """One all-day event per issued, still-open invoice on its due date (§33).

    Finance is permission-controlled (spec §98) and the agenda is all-staff — so
    this source is empty for anyone without ``finance.view`` (unlike hearings /
    tasks / contracts, which are all-staff)."""
    from core.permissions.capabilities import Capability, can

    if not can(user, Capability.FINANCE_VIEW):
        return []
    invoices = (
        Invoice.objects.for_user(user)
        .open()
        .filter(due_date__isnull=False, due_date__gte=start.date(), due_date__lt=end.date())
        .select_related("client", "case")
        .with_balances()
    )
    return [_invoice_event(i) for i in invoices]
