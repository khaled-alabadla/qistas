"""
Report builders (spec §43) — the read layer.

Each ``build_*_report(*, user, filters)`` returns a
:class:`reports.framework.ReportResult`. Every query goes through the owning
domain's ``for_user()``-scoped manager (spec Phase 10 §6); financial builders
additionally reuse Finance's own helpers and never re-implement a total
(spec Phase 10 §9). Currencies are never summed across each other
(spec Phase 10 §10, ADR-0032).

Rows are capped at :data:`reports.framework.MAX_ROWS`; a capped result is marked
``truncated`` and the UI asks the user to narrow the filters.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from cases.models import TERMINAL_STATUSES, Case, CasePriority, CaseStatus
from clients.models import Client, ClientStatus, ClientType
from core.money import ZERO, quantize
from finance.models import (
    CreditNote,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PaymentReversal,
)
from finance.selectors import _invoice_totals_by_currency
from hearings.models import Hearing, HearingStatus, HearingType
from reports.framework import (
    BADGE,
    DATE,
    DATETIME,
    MAX_ROWS,
    MONEY,
    NUM,
    TEXT,
    Cell,
    Column,
    CurrencyTotals,
    Metric,
    ReportResult,
    date_range_filter,
    datetime_range_filter,
    person_name,
)
from tasks.models import Deadline, DeadlineStatus, Task, TaskStatus

_MONEY_ZERO = Decimal("0.00")


def _cap(rows: list) -> tuple[list, bool]:
    if len(rows) > MAX_ROWS:
        return rows[:MAX_ROWS], True
    return rows, False


_TONE_BY_STATUS = {
    "danger": {"missed", "cancelled"},
    "success": {"paid", "held", "met", "done", "concluded"},
    "warning": {"partially_paid", "postponed", "on_hold", "pending", "unpaid"},
}


def _status_tone(value: str) -> str:
    for tone, names in _TONE_BY_STATUS.items():
        if value in names:
            return tone
    return "neutral"


def _counts(qs, field: str, *, distinct: bool = False) -> dict:
    """``{value: row_count}`` grouped by ``field``.

    ``.order_by()`` first — an ordering inherited from the row queryset would
    silently widen the ``GROUP BY`` (one row per ``(field, order_field)``) and
    inflate the breakdown. Aggregate annotations already on ``qs`` regroup to
    ``field`` and are harmless; non-aggregate annotations must not be present.
    """
    grouped = qs.order_by().values(field).annotate(n=Count("pk", distinct=distinct))
    return {r[field]: r["n"] for r in grouped}


def _client_ids_with_active_cases(user, active_case_q):
    return (
        Client.objects.for_user(user)
        .annotate(_ac=Count("cases", filter=active_case_q, distinct=True))
        .filter(_ac__gt=0)
        .values("pk")
    )


# ── Cases ─────────────────────────────────────────────────────────────────
def build_case_report(*, user, filters: dict) -> ReportResult:
    qs = Case.objects.for_user(user).select_related("client", "type", "assigned_lawyer", "court")

    status = filters.get("status") or ""
    if status:
        qs = qs.filter(status=status)
    elif filters.get("open_only", True):
        qs = qs.exclude(status__in=list(TERMINAL_STATUSES))
    if filters.get("priority"):
        qs = qs.filter(priority=filters["priority"])
    if filters.get("case_type"):
        qs = qs.filter(type=filters["case_type"])
    if filters.get("lawyer"):
        qs = qs.filter(assigned_lawyer=filters["lawyer"])
    if filters.get("court"):
        qs = qs.filter(court=filters["court"])
    if filters.get("client"):
        qs = qs.filter(client=filters["client"])

    d_from, d_to = filters.get("date_from"), filters.get("date_to")
    qs = qs.filter(**datetime_range_filter("created_at", d_from, d_to))
    qs = qs.order_by("-created_at")

    status_labels = dict(CaseStatus.choices)
    priority_labels = dict(CasePriority.choices)

    all_rows = list(qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)

    rows: list[list[Cell]] = []
    for c in page:
        rows.append(
            [
                Cell(c.case_number, TEXT, href=reverse("cases:detail", args=[c.pk])),
                Cell(c.title, TEXT),
                Cell(c.client.display_name if c.client_id else "—", TEXT),
                Cell(c.type.name if c.type_id else "—", TEXT),
                Cell(status_labels.get(c.status, c.status), BADGE, tone=_status_tone(c.status)),
                Cell(
                    priority_labels.get(c.priority, c.priority),
                    BADGE,
                    tone="danger" if c.priority == CasePriority.URGENT else "neutral",
                ),
                Cell(
                    person_name(c.assigned_lawyer) if c.assigned_lawyer_id else _("غير مُسندة"), TEXT
                ),
                Cell(c.court.name if c.court_id else "—", TEXT),
                Cell(c.created_at, DATE),
            ]
        )

    # Breakdowns — bounded aggregate queries, independent of the row cap.
    by_status = _counts(qs, "status")
    by_priority = _counts(qs, "priority")
    total = sum(by_status.values())

    metrics = [Metric(_("إجمالي القضايا"), total, NUM)]
    for value, label in CaseStatus.choices:
        if by_status.get(value):
            metrics.append(Metric(label, by_status[value], NUM))
    for value, label in CasePriority.choices:
        if by_priority.get(value):
            tone = "danger" if value == CasePriority.URGENT else None
            metrics.append(Metric(_("أولوية: %(p)s") % {"p": label}, by_priority[value], NUM, tone))

    return ReportResult(
        columns=[
            Column(_("رقم القضية")),
            Column(_("العنوان")),
            Column(_("الموكل")),
            Column(_("النوع")),
            Column(_("الحالة"), BADGE),
            Column(_("الأولوية"), BADGE),
            Column(_("المحامي")),
            Column(_("المحكمة")),
            Column(_("تاريخ الفتح"), DATE),
        ],
        rows=rows,
        metrics=metrics,
        notes=[_("«تاريخ الفتح» هو تاريخ تسجيل القضية في النظام.")],
        truncated=truncated,
    )


# ── Clients ───────────────────────────────────────────────────────────────
def build_client_report(*, user, filters: dict) -> ReportResult:
    active_case_q = ~Q(cases__status__in=list(TERMINAL_STATUSES))

    base = Client.objects.for_user(user)  # no annotations → clean GROUP BY for metrics
    if filters.get("client_type"):
        base = base.filter(type=filters["client_type"])
    if filters.get("status"):
        base = base.filter(status=filters["status"])
    with_active = bool(filters.get("with_active_cases"))
    if with_active:
        base = base.filter(pk__in=_client_ids_with_active_cases(user, active_case_q))

    rows_qs = base.annotate(
        active_cases=Count("cases", filter=active_case_q, distinct=True),
        total_cases=Count("cases", distinct=True),
    ).order_by("company_name", "full_name", "client_number")

    type_labels = dict(ClientType.choices)
    status_labels = dict(ClientStatus.choices)

    all_rows = list(rows_qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)
    rows: list[list[Cell]] = []
    for cl in page:
        rows.append(
            [
                Cell(cl.client_number, TEXT, href=reverse("clients:detail", args=[cl.pk])),
                Cell(cl.display_name, TEXT),
                Cell(type_labels.get(cl.type, cl.type), TEXT),
                Cell(
                    status_labels.get(cl.status, cl.status),
                    BADGE,
                    tone="neutral" if cl.status != ClientStatus.ACTIVE else "success",
                ),
                Cell(cl.active_cases, NUM),
                Cell(cl.total_cases, NUM),
            ]
        )

    # Headline metrics — over `base` (no non-aggregate annotations → clean
    # GROUP BY), independent of the row cap.
    by_status = _counts(base, "status")
    active_ids = _client_ids_with_active_cases(user, active_case_q)
    metrics = [
        Metric(_("إجمالي العملاء"), base.count(), NUM),
        Metric(_("لديهم قضايا نشطة"), base.filter(pk__in=active_ids).count(), NUM),
        Metric(ClientStatus.ACTIVE.label, by_status.get(ClientStatus.ACTIVE, 0), NUM),
        Metric(ClientStatus.PROSPECT.label, by_status.get(ClientStatus.PROSPECT, 0), NUM),
        Metric(ClientStatus.ARCHIVED.label, by_status.get(ClientStatus.ARCHIVED, 0), NUM),
    ]

    return ReportResult(
        columns=[
            Column(_("رقم العميل")),
            Column(_("الاسم")),
            Column(_("النوع")),
            Column(_("الحالة"), BADGE),
            Column(_("قضايا نشطة"), NUM),
            Column(_("إجمالي القضايا"), NUM),
        ],
        rows=rows,
        metrics=metrics,
        truncated=truncated,
    )


# ── Hearings ──────────────────────────────────────────────────────────────
def build_hearing_report(*, user, filters: dict) -> ReportResult:
    qs = Hearing.objects.for_user(user).select_related("case", "case__client", "court", "lawyer")
    if filters.get("status"):
        qs = qs.filter(status=filters["status"])
    if filters.get("court"):
        qs = qs.filter(court=filters["court"])
    if filters.get("lawyer"):
        qs = qs.filter(lawyer=filters["lawyer"])
    if filters.get("client"):
        qs = qs.filter(case__client=filters["client"])

    d_from, d_to = filters.get("date_from"), filters.get("date_to")
    qs = qs.filter(**datetime_range_filter("scheduled_at", d_from, d_to))
    qs = qs.order_by("scheduled_at")

    status_labels = dict(HearingStatus.choices)
    type_labels = dict(HearingType.choices)

    all_rows = list(qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)
    rows: list[list[Cell]] = []
    for h in page:
        rows.append(
            [
                Cell(h.scheduled_at, DATETIME, href=reverse("hearings:detail", args=[h.pk])),
                Cell(h.case.case_number if h.case_id else "—", TEXT),
                Cell(h.case.client.display_name if h.case_id and h.case.client_id else "—", TEXT),
                Cell(h.court.name if h.court_id else "—", TEXT),
                Cell(type_labels.get(h.hearing_type, h.hearing_type), TEXT),
                Cell(status_labels.get(h.status, h.status), BADGE, tone=_status_tone(h.status)),
                Cell(person_name(h.lawyer) if h.lawyer_id else "—", TEXT),
            ]
        )

    by_status = _counts(qs, "status")
    metrics = [Metric(_("إجمالي الجلسات"), sum(by_status.values()), NUM)]
    for value, label in HearingStatus.choices:
        metrics.append(Metric(label, by_status.get(value, 0), NUM))

    return ReportResult(
        columns=[
            Column(_("الموعد"), DATETIME),
            Column(_("القضية")),
            Column(_("الموكل")),
            Column(_("المحكمة")),
            Column(_("النوع")),
            Column(_("الحالة"), BADGE),
            Column(_("المحامي")),
        ],
        rows=rows,
        metrics=metrics,
        truncated=truncated,
    )


# ── Tasks ─────────────────────────────────────────────────────────────────
def build_task_report(*, user, filters: dict) -> ReportResult:
    qs = Task.objects.for_user(user).alive().select_related("assigned_to", "case", "client")
    if filters.get("status"):
        qs = qs.filter(status=filters["status"])
    if filters.get("assigned_to"):
        qs = qs.filter(assigned_to=filters["assigned_to"])
    if filters.get("priority"):
        qs = qs.filter(priority=filters["priority"])

    today = timezone.localdate()
    open_statuses = [TaskStatus.NEW, TaskStatus.IN_PROGRESS]
    if filters.get("overdue_only"):
        qs = qs.filter(status__in=open_statuses, due_date__isnull=False, due_date__lt=today)

    d_from, d_to = filters.get("date_from"), filters.get("date_to")
    qs = qs.filter(**date_range_filter("due_date", d_from, d_to))
    qs = qs.order_by("due_date", "-created_at")

    status_labels = dict(TaskStatus.choices)

    all_rows = list(qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)
    rows: list[list[Cell]] = []
    overdue_count = 0
    for t in page:
        is_overdue = t.status in open_statuses and t.due_date is not None and t.due_date < today
        overdue_count += int(is_overdue)
        link = t.case.case_number if t.case_id else (t.client.display_name if t.client_id else "—")
        rows.append(
            [
                Cell(t.title, TEXT, href=reverse("tasks:detail", args=[t.pk])),
                Cell(link, TEXT),
                Cell(person_name(t.assigned_to) if t.assigned_to_id else "—", TEXT),
                Cell(t.get_priority_display(), TEXT),
                Cell(status_labels.get(t.status, t.status), BADGE, tone=_status_tone(t.status)),
                Cell(t.due_date, DATE),
                Cell(
                    _("نعم") if is_overdue else _("لا"),
                    BADGE,
                    tone="danger" if is_overdue else "neutral",
                ),
            ]
        )

    by_status = _counts(qs, "status")
    by_employee = (
        qs.order_by()
        .values("assigned_to__first_name", "assigned_to__last_name", "assigned_to__email")
        .annotate(n=Count("pk"))
        .order_by("-n")[:10]
    )
    metrics = [Metric(_("إجمالي المهام"), sum(by_status.values()), NUM)]
    for value, label in TaskStatus.choices:
        metrics.append(Metric(label, by_status.get(value, 0), NUM))
    metrics.append(
        Metric(_("متأخرة (ضمن المعروض)"), overdue_count, NUM, "danger" if overdue_count else None)
    )
    for r in by_employee:
        name = f"{r['assigned_to__first_name']} {r['assigned_to__last_name']}".strip() or (
            r["assigned_to__email"] or _("غير مُسندة")
        )
        metrics.append(Metric(_("للموظف: %(n)s") % {"n": name}, r["n"], NUM))

    return ReportResult(
        columns=[
            Column(_("المهمة")),
            Column(_("القضية/الموكل")),
            Column(_("الموظف")),
            Column(_("الأولوية")),
            Column(_("الحالة"), BADGE),
            Column(_("الاستحقاق"), DATE),
            Column(_("متأخرة؟"), BADGE),
        ],
        rows=rows,
        metrics=metrics,
        notes=[_("«متأخرة» تُحتسب لحظيًا: مهمة مفتوحة تجاوز تاريخ استحقاقها اليوم (ADR-0006).")],
        truncated=truncated,
    )


# ── Deadlines ─────────────────────────────────────────────────────────────
def build_deadline_report(*, user, filters: dict) -> ReportResult:
    qs = Deadline.objects.for_user(user).select_related("case", "case__client")
    if filters.get("status"):
        qs = qs.filter(status=filters["status"])

    today = timezone.localdate()
    if filters.get("overdue_only"):
        qs = qs.filter(status=DeadlineStatus.PENDING, due_date__lt=today)

    d_from, d_to = filters.get("date_from"), filters.get("date_to")
    qs = qs.filter(**date_range_filter("due_date", d_from, d_to))
    qs = qs.order_by("due_date")

    status_labels = dict(DeadlineStatus.choices)

    all_rows = list(qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)
    rows: list[list[Cell]] = []
    overdue_count = 0
    for d in page:
        is_overdue = d.status == DeadlineStatus.PENDING and d.due_date < today
        overdue_count += int(is_overdue)
        rows.append(
            [
                Cell(d.title, TEXT, href=reverse("tasks:deadline_detail", args=[d.pk])),
                Cell(d.case.case_number if d.case_id else "—", TEXT),
                Cell(status_labels.get(d.status, d.status), BADGE, tone=_status_tone(d.status)),
                Cell(d.due_date, DATE),
                Cell(
                    _("نعم") if is_overdue else _("لا"),
                    BADGE,
                    tone="danger" if is_overdue else "neutral",
                ),
            ]
        )

    by_status = _counts(qs, "status")
    metrics = [Metric(_("إجمالي المواعيد"), sum(by_status.values()), NUM)]
    for value, label in DeadlineStatus.choices:
        metrics.append(Metric(label, by_status.get(value, 0), NUM))
    metrics.append(
        Metric(_("فائتة (ضمن المعروض)"), overdue_count, NUM, "danger" if overdue_count else None)
    )

    return ReportResult(
        columns=[
            Column(_("الموعد النهائي")),
            Column(_("القضية")),
            Column(_("الحالة"), BADGE),
            Column(_("الاستحقاق"), DATE),
            Column(_("فائت؟"), BADGE),
        ],
        rows=rows,
        metrics=metrics,
        truncated=truncated,
    )


# ── Finance: shared filter application ────────────────────────────────────
def _apply_finance_scope(
    qs, filters, *, client_path="client", case_path="case", ccy_path="currency"
):
    if filters.get("currency"):
        qs = qs.filter(**{ccy_path: filters["currency"]})
    if filters.get("client"):
        qs = qs.filter(**{client_path: filters["client"]})
    if filters.get("case"):
        qs = qs.filter(**{case_path: filters["case"]})
    return qs


# ── Finance: Revenue ─────────────────────────────────────────────────────
def build_revenue_report(*, user, filters: dict) -> ReportResult:
    d_from, d_to = filters.get("date_from"), filters.get("date_to")
    scoped = Invoice.objects.for_user(user)
    scoped = _apply_finance_scope(scoped, filters)
    issued = scoped.exclude(status__in=[InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED]).filter(
        **date_range_filter("issue_date", d_from, d_to)
    )

    rows_qs = (
        issued.select_related("client", "case")
        .with_balances()
        .order_by("-issue_date", "-invoice_number")
    )
    all_rows = list(rows_qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)

    status_labels = dict(InvoiceStatus.choices)
    rows: list[list[Cell]] = []
    for inv in page:
        rows.append(
            [
                Cell(
                    inv.invoice_number,
                    TEXT,
                    href=reverse("finance:invoice_detail", args=[inv.pk]),
                ),
                Cell(inv.client.display_name if inv.client_id else "—", TEXT),
                Cell(inv.case.case_number if inv.case_id else "—", TEXT),
                Cell(inv.issue_date, DATE),
                Cell(inv.currency, TEXT),
                Cell(
                    status_labels.get(inv.status, inv.status), BADGE, tone=_status_tone(inv.status)
                ),
                Cell(quantize(inv.total), MONEY, currency=inv.currency),
                Cell(quantize(inv.amount_paid), MONEY, currency=inv.currency),
                Cell(inv.outstanding, MONEY, currency=inv.currency),
            ]
        )

    totals = _invoice_totals_by_currency(issued)
    counts = _counts(issued, "currency")
    currency_totals = [
        CurrencyTotals(
            currency=t["currency"],
            items=[
                (_("عدد الفواتير"), Decimal(counts.get(t["currency"], 0))),
                (_("إجمالي الفواتير"), t["invoiced"]),
                (_("إشعارات دائنة"), t["credited"]),
                (_("المحصّل"), t["paid"]),
                (_("المتبقي"), t["outstanding"]),
            ],
        )
        for t in totals
    ]

    return ReportResult(
        columns=[
            Column(_("رقم الفاتورة")),
            Column(_("الموكل")),
            Column(_("القضية")),
            Column(_("تاريخ الإصدار"), DATE),
            Column(_("العملة")),
            Column(_("الحالة"), BADGE),
            Column(_("الإجمالي"), MONEY),
            Column(_("المحصّل"), MONEY),
            Column(_("المتبقي"), MONEY),
        ],
        rows=rows,
        metrics=[Metric(_("عدد الفواتير الصادرة"), issued.count(), NUM)],
        currency_totals=currency_totals,
        notes=[
            _("الفواتير الصادرة فقط (تستثنى المسودّات والملغاة). العملات لا تُجمع معًا (ADR-0032)."),
        ],
        truncated=truncated,
    )


# ── Finance: Payments ────────────────────────────────────────────────────
def build_payment_report(*, user, filters: dict) -> ReportResult:
    d_from, d_to = filters.get("date_from"), filters.get("date_to")
    scoped = Payment.objects.for_user(user).select_related(
        "invoice", "invoice__client", "invoice__case"
    )
    scoped = _apply_finance_scope(
        scoped,
        filters,
        client_path="invoice__client",
        case_path="invoice__case",
        ccy_path="invoice__currency",
    )
    if filters.get("method"):
        scoped = scoped.filter(method=filters["method"])
    payments = scoped.filter(**date_range_filter("paid_on", d_from, d_to))

    rows_qs = payments.annotate(_rev=Coalesce(Sum("reversals__amount"), _MONEY_ZERO)).order_by(
        "-paid_on", "-created_at"
    )
    all_rows = list(rows_qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)

    method_labels = dict(PaymentMethod.choices)
    rows: list[list[Cell]] = []
    for p in page:
        ccy = p.invoice.currency
        rev = quantize(p._rev)
        net = quantize(p.amount - rev)
        rows.append(
            [
                Cell(p.reference, TEXT, href=reverse("finance:payment_detail", args=[p.pk])),
                Cell(p.invoice.invoice_number if p.invoice_id else "—", TEXT),
                Cell(
                    p.invoice.client.display_name if p.invoice_id and p.invoice.client_id else "—",
                    TEXT,
                ),
                Cell(p.paid_on, DATE),
                Cell(ccy, TEXT),
                Cell(method_labels.get(p.method, p.method), TEXT),
                Cell(quantize(p.amount), MONEY, currency=ccy),
                Cell(rev, MONEY, currency=ccy),
                Cell(net, MONEY, currency=ccy),
            ]
        )

    # Per-currency totals in TWO queries (never fan `amount` over the reversal join).
    gross = {
        r["invoice__currency"]: r["g"]
        for r in payments.values("invoice__currency").annotate(
            g=Coalesce(Sum("amount"), _MONEY_ZERO)
        )
    }
    revs = {
        r["payment__invoice__currency"]: r["r"]
        for r in PaymentReversal.objects.filter(payment__in=payments)
        .values("payment__invoice__currency")
        .annotate(r=Coalesce(Sum("amount"), _MONEY_ZERO))
    }
    currency_totals = []
    for ccy in sorted(gross):
        g = quantize(gross[ccy])
        r = quantize(revs.get(ccy) or ZERO)
        currency_totals.append(
            CurrencyTotals(
                currency=ccy,
                items=[
                    (_("إجمالي الدفعات"), g),
                    (_("استرجاعات"), r),
                    (_("الصافي"), quantize(g - r)),
                ],
            )
        )

    return ReportResult(
        columns=[
            Column(_("مرجع الدفعة")),
            Column(_("الفاتورة")),
            Column(_("الموكل")),
            Column(_("تاريخ الدفع"), DATE),
            Column(_("العملة")),
            Column(_("الطريقة")),
            Column(_("المبلغ"), MONEY),
            Column(_("استرجاع"), MONEY),
            Column(_("الصافي"), MONEY),
        ],
        rows=rows,
        currency_totals=currency_totals,
        notes=[_("المبالغ صافية بعد الاسترجاعات. العملات لا تُجمع معًا (ADR-0032).")],
        truncated=truncated,
    )


# ── Finance: Outstanding invoices (aging) ────────────────────────────────
_AGING_BUCKETS = (
    (_("غير مستحقة/0–30"), 0, 30),
    (_("31–60"), 31, 60),
    (_("61–90"), 61, 90),
    (_("أكثر من 90"), 91, 10**9),
)


def build_outstanding_report(*, user, filters: dict) -> ReportResult:
    scoped = Invoice.objects.for_user(user).open().with_balances().select_related("client", "case")
    scoped = _apply_finance_scope(scoped, filters)
    today = timezone.localdate()
    if filters.get("overdue_only"):
        scoped = scoped.filter(due_date__isnull=False, due_date__lt=today)
    rows_qs = scoped.order_by("due_date")

    all_rows = list(rows_qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)

    status_labels = dict(InvoiceStatus.choices)
    rows: list[list[Cell]] = []
    # aging accumulation from the displayed rows (per currency, per bucket)
    aging: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO])
    for inv in page:
        days = (today - inv.due_date).days if inv.due_date else 0
        days = max(days, 0)
        bucket = next(i for i, (_l, lo, hi) in enumerate(_AGING_BUCKETS) if lo <= days <= hi)
        outstanding = inv.outstanding
        aging[inv.currency][bucket] += outstanding
        rows.append(
            [
                Cell(
                    inv.invoice_number, TEXT, href=reverse("finance:invoice_detail", args=[inv.pk])
                ),
                Cell(inv.client.display_name if inv.client_id else "—", TEXT),
                Cell(inv.case.case_number if inv.case_id else "—", TEXT),
                Cell(inv.issue_date, DATE),
                Cell(inv.due_date, DATE),
                Cell(inv.currency, TEXT),
                Cell(
                    status_labels.get(inv.status, inv.status), BADGE, tone=_status_tone(inv.status)
                ),
                Cell(days if inv.due_date and days > 0 else 0, NUM),
                Cell(quantize(inv.total), MONEY, currency=inv.currency),
                Cell(outstanding, MONEY, currency=inv.currency),
            ]
        )

    # Accurate per-currency outstanding (independent of the row cap).
    totals = _invoice_totals_by_currency(scoped)
    currency_totals = []
    for t in totals:
        ccy = t["currency"]
        buckets = aging.get(ccy, [ZERO, ZERO, ZERO, ZERO])
        items = [(_("إجمالي المتبقي"), t["outstanding"])]
        items += [
            (label, quantize(buckets[i])) for i, (label, _lo, _hi) in enumerate(_AGING_BUCKETS)
        ]
        currency_totals.append(CurrencyTotals(currency=ccy, items=items))

    return ReportResult(
        columns=[
            Column(_("رقم الفاتورة")),
            Column(_("الموكل")),
            Column(_("القضية")),
            Column(_("الإصدار"), DATE),
            Column(_("الاستحقاق"), DATE),
            Column(_("العملة")),
            Column(_("الحالة"), BADGE),
            Column(_("أيام التأخر"), NUM),
            Column(_("الإجمالي"), MONEY),
            Column(_("المتبقي"), MONEY),
        ],
        rows=rows,
        currency_totals=currency_totals,
        notes=[
            _("الفواتير المفتوحة فقط، بحسب تاريخ اليوم. توزيع الأعمار محسوب من الصفوف المعروضة."),
        ],
        truncated=truncated,
    )


# ── Finance: Expenses ────────────────────────────────────────────────────
def build_expense_report(*, user, filters: dict) -> ReportResult:
    d_from, d_to = filters.get("date_from"), filters.get("date_to")
    scoped = Expense.objects.for_user(user).alive().select_related("case", "client")
    scoped = _apply_finance_scope(scoped, filters)
    if filters.get("category"):
        scoped = scoped.filter(category=filters["category"])
    expenses = scoped.filter(**date_range_filter("spent_on", d_from, d_to))
    rows_qs = expenses.order_by("-spent_on", "-created_at")

    all_rows = list(rows_qs[: MAX_ROWS + 1])
    page, truncated = _cap(all_rows)

    cat_labels = dict(ExpenseCategory.choices)
    rows: list[list[Cell]] = []
    for e in page:
        rows.append(
            [
                Cell(e.reference, TEXT, href=reverse("finance:expense_detail", args=[e.pk])),
                Cell(e.description, TEXT),
                Cell(cat_labels.get(e.category, e.category), TEXT),
                Cell(e.case.case_number if e.case_id else "—", TEXT),
                Cell(e.client.display_name if e.client_id else "—", TEXT),
                Cell(e.spent_on, DATE),
                Cell(e.currency, TEXT),
                Cell(quantize(e.amount), MONEY, currency=e.currency),
            ]
        )

    per_ccy = {
        r["currency"]: r["t"]
        for r in expenses.values("currency").annotate(t=Coalesce(Sum("amount"), _MONEY_ZERO))
    }
    per_ccy_cat = defaultdict(lambda: defaultdict(lambda: ZERO))
    for r in expenses.values("currency", "category").annotate(
        t=Coalesce(Sum("amount"), _MONEY_ZERO)
    ):
        per_ccy_cat[r["currency"]][r["category"]] = r["t"]

    currency_totals = []
    for ccy in sorted(per_ccy):
        items = [(_("إجمالي المصروفات"), quantize(per_ccy[ccy]))]
        for value, label in ExpenseCategory.choices:
            amt = per_ccy_cat[ccy].get(value)
            if amt:
                items.append((label, quantize(amt)))
        currency_totals.append(CurrencyTotals(currency=ccy, items=items))

    return ReportResult(
        columns=[
            Column(_("المرجع")),
            Column(_("الوصف")),
            Column(_("التصنيف")),
            Column(_("القضية")),
            Column(_("الموكل")),
            Column(_("تاريخ الصرف"), DATE),
            Column(_("العملة")),
            Column(_("المبلغ"), MONEY),
        ],
        rows=rows,
        currency_totals=currency_totals,
        notes=[_("المصروفات النشطة فقط (تستثنى المسحوبة). العملات لا تُجمع معًا (ADR-0032).")],
        truncated=truncated,
    )


# ── Finance: Case financial performance ──────────────────────────────────
def build_case_financials_report(*, user, filters: dict) -> ReportResult:
    d_from, d_to = filters.get("date_from"), filters.get("date_to")

    inv_scope = _apply_finance_scope(Invoice.objects.for_user(user), filters)
    inv_scope = inv_scope.exclude(status__in=[InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED])
    if d_from or d_to:
        inv_scope = inv_scope.filter(**date_range_filter("issue_date", d_from, d_to))

    exp_scope = _apply_finance_scope(Expense.objects.for_user(user).alive(), filters)
    if d_from or d_to:
        exp_scope = exp_scope.filter(**date_range_filter("spent_on", d_from, d_to))

    # keyed by (case_id or None, currency)
    agg: dict[tuple, dict] = defaultdict(
        lambda: {"invoiced": ZERO, "paid": ZERO, "credited": ZERO, "expenses": ZERO}
    )
    case_meta: dict = {}

    for r in inv_scope.values(
        "case_id",
        "case__case_number",
        "case__title",
        "case__client__full_name",
        "case__client__company_name",
        "currency",
    ).annotate(
        invoiced=Coalesce(Sum("total"), _MONEY_ZERO),
        paid=Coalesce(Sum("amount_paid"), _MONEY_ZERO),
    ):
        key = (r["case_id"], r["currency"])
        agg[key]["invoiced"] += r["invoiced"]
        agg[key]["paid"] += r["paid"]
        case_meta[r["case_id"]] = (
            r["case__case_number"],
            r["case__title"],
            r["case__client__company_name"] or r["case__client__full_name"] or "—",
        )

    for r in (
        CreditNote.objects.filter(invoice__in=inv_scope)
        .values("invoice__case_id", "invoice__currency")
        .annotate(c=Coalesce(Sum("amount"), _MONEY_ZERO))
    ):
        agg[(r["invoice__case_id"], r["invoice__currency"])]["credited"] += r["c"]

    for r in exp_scope.values("case_id", "case__case_number", "case__title", "currency").annotate(
        e=Coalesce(Sum("amount"), _MONEY_ZERO)
    ):
        key = (r["case_id"], r["currency"])
        agg[key]["expenses"] += r["e"]
        case_meta.setdefault(r["case_id"], (r["case__case_number"], r["case__title"], "—"))

    ordered = sorted(
        agg.items(),
        key=lambda kv: (case_meta.get(kv[0][0], ("",))[0] or "", kv[0][1]),
    )
    ordered, truncated = _cap(ordered)

    rows: list[list[Cell]] = []
    per_ccy = defaultdict(
        lambda: {"invoiced": ZERO, "paid": ZERO, "outstanding": ZERO, "expenses": ZERO}
    )
    for (case_id, ccy), v in ordered:
        invoiced = quantize(v["invoiced"])
        paid = quantize(v["paid"])
        credited = quantize(v["credited"])
        outstanding = quantize(max(invoiced - credited - paid, ZERO))
        expenses = quantize(v["expenses"])
        num, title, client = case_meta.get(case_id, ("—", "—", "—"))
        href = reverse("cases:detail", args=[case_id]) if case_id else None
        rows.append(
            [
                Cell(num or "—", TEXT, href=href),
                Cell(title or "—", TEXT),
                Cell(client, TEXT),
                Cell(ccy, TEXT),
                Cell(invoiced, MONEY, currency=ccy),
                Cell(credited, MONEY, currency=ccy),
                Cell(paid, MONEY, currency=ccy),
                Cell(outstanding, MONEY, currency=ccy),
                Cell(expenses, MONEY, currency=ccy),
            ]
        )
        p = per_ccy[ccy]
        p["invoiced"] += invoiced
        p["paid"] += paid
        p["outstanding"] += outstanding
        p["expenses"] += expenses

    currency_totals = [
        CurrencyTotals(
            currency=ccy,
            items=[
                (_("إجمالي ما فُوتر"), quantize(v["invoiced"])),
                (_("إجمالي المحصّل"), quantize(v["paid"])),
                (_("إجمالي المتبقي"), quantize(v["outstanding"])),
                (_("إجمالي المصروفات"), quantize(v["expenses"])),
            ],
        )
        for ccy, v in sorted(per_ccy.items())
    ]

    return ReportResult(
        columns=[
            Column(_("رقم القضية")),
            Column(_("العنوان")),
            Column(_("الموكل")),
            Column(_("العملة")),
            Column(_("فُوتر")),
            Column(_("إشعارات دائنة"), MONEY),
            Column(_("محصّل"), MONEY),
            Column(_("متبقٍ"), MONEY),
            Column(_("مصروفات"), MONEY),
        ],
        rows=rows,
        currency_totals=currency_totals,
        notes=[
            _("سطر لكل (قضية × عملة). المصروفات مستقلة ولا تُخصم من المفوتر (ADR-0013)."),
            _("العملات لا تُجمع معًا (ADR-0032). الفواتير الصادرة فقط."),
        ],
        truncated=truncated,
    )
