"""
The operational dashboard — a **read/analytics layer** over the existing domains
(spec §17–19, docs/adr/0033). It owns **no domain data**: every figure is an
aggregate or a bounded slice of `cases` / `clients` / `hearings` / `tasks` /
`documents` / `contracts` / `finance`, always through those domains' own
`for_user()`-scoped managers and existing selectors.

**Every widget is capability-gated in the *query*, not just hidden in the
template.** A user only sees a domain's numbers if they hold that domain's
`*.view` capability — finance is the strict one (Phase 8: finance is not
all-staff, spec §98), but cases / hearings / tasks / contracts / clients are
checked too (§5 — "do not assume dashboard access = access to every domain").
`recent_activity` is filtered to the domains the viewer may see, and the
confidential-case audit action is always excluded for non-`view_confidential`.

Query budget: `build_dashboard(user)` runs a **bounded** number of queries,
**flat** regardless of how much data the office holds, and never re-runs an
identical query. See `dashboard/tests/test_performance.py`.
"""

from __future__ import annotations

from django.db.models import Count
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from audit.models import AuditAction, AuditLog
from cases.models import Case, CasePriority, CaseStatus
from clients.models import Client
from contracts.selectors import expiring_contracts
from core.permissions.capabilities import Capability
from finance.selectors import firm_financials, outstanding_invoices, overdue_invoices
from hearings.selectors import today_hearings, upcoming_hearings
from tasks.models import Deadline
from tasks.selectors import overdue_tasks, upcoming_deadlines

ATTENTION_HEARING_DAYS = 7
DEADLINE_HORIZON_DAYS = 14
EXPIRING_CONTRACT_DAYS = 30
_LIST_LIMIT = 6

# Recent-activity allowlist (spec §19): creations + lifecycle changes only — not
# auth events, not noisy field edits. Grouped by the capability that gates them.
_ACTIVITY_BY_CAP: dict[str, tuple[str, ...]] = {
    Capability.CLIENTS_VIEW: (AuditAction.CLIENT_CREATED, AuditAction.CLIENT_ARCHIVED),
    Capability.CASES_VIEW: (AuditAction.CASE_CREATED, AuditAction.CASE_STATUS_CHANGED),
    Capability.HEARINGS_VIEW: (
        AuditAction.HEARING_SCHEDULED,
        AuditAction.HEARING_HELD,
        AuditAction.HEARING_RESCHEDULED,
        AuditAction.HEARING_POSTPONED,
        AuditAction.HEARING_CANCELLED,
    ),
    Capability.TASKS_VIEW: (
        AuditAction.TASK_CREATED,
        AuditAction.TASK_STATUS_CHANGED,
        AuditAction.DEADLINE_CREATED,
        AuditAction.DEADLINE_STATUS_CHANGED,
    ),
    Capability.DOCUMENTS_VIEW: (AuditAction.DOCUMENT_UPLOADED, AuditAction.DOCUMENT_RETIRED),
    Capability.CONTRACTS_VIEW: (
        AuditAction.CONTRACT_CREATED,
        AuditAction.CONTRACT_STATUS_CHANGED,
    ),
    Capability.FINANCE_VIEW: (
        AuditAction.FEE_AGREEMENT_CREATED,
        AuditAction.INVOICE_ISSUED,
        AuditAction.PAYMENT_RECORDED,
        AuditAction.CREDIT_NOTE_ISSUED,
        AuditAction.EXPENSE_CREATED,
    ),
}
_ENTITY_URL: dict[str, str] = {
    "clients.client": "clients:detail",
    "cases.case": "cases:detail",
    "hearings.hearing": "hearings:detail",
    "tasks.task": "tasks:detail",
    "tasks.deadline": "tasks:deadline_detail",
    "documents.document": "documents:detail",
    "contracts.contract": "contracts:detail",
    "finance.invoice": "finance:invoice_detail",
    "finance.payment": "finance:payment_detail",
    "finance.feeagreement": "finance:fee_agreement_detail",
    "finance.expense": "finance:expense_detail",
}


def _url(name: str, *, args=None, query: str = "") -> str | None:
    try:
        url = reverse(name, args=args or [])
    except NoReverseMatch:
        return None
    return f"{url}?{query}" if query else url


def _list(items, *, total: int | None = None) -> tuple[int, list]:
    """Evaluate a bounded slice once. When ``total`` is already known (computed
    in ``_shared_counts``) reuse it; otherwise derive the count from the same
    fetch when the slice is complete, else one extra COUNT."""
    rows = list(items[: _LIST_LIMIT + 1])
    if total is not None:
        return total, rows[:_LIST_LIMIT]
    if len(rows) <= _LIST_LIMIT:
        return len(rows), rows
    return items.count(), rows[:_LIST_LIMIT]


def _block(key, label, tone, qs, render, all_url, *, total: int | None = None) -> dict:
    count, rows = _list(qs, total=total)
    return {
        "key": key,
        "label": label,
        "tone": tone,
        "count": count,
        "items": [render(r) for r in rows],
        "all_url": all_url,
    }


# ── Shared counts (spec §10 — computed once, feed both KPIs and attention) ──
def _shared_counts(user, caps: set[str]) -> dict[str, int]:
    """The figures the KPI row and the attention blocks both need. Computed once
    here — never as a side effect of another helper — so the two can never
    disagree and no count query runs twice (`_block(total=...)` reuses these)."""
    counts: dict[str, int] = {}
    if Capability.CASES_VIEW in caps:
        open_cases = Case.objects.for_user(user).open()
        counts["active_cases"] = open_cases.count()
        counts["urgent_cases"] = open_cases.filter(priority=CasePriority.URGENT).count()
    if Capability.TASKS_VIEW in caps:
        counts["overdue_tasks"] = overdue_tasks(user).count()
    if Capability.CONTRACTS_VIEW in caps:
        counts["expiring_contracts"] = expiring_contracts(user, days=EXPIRING_CONTRACT_DAYS).count()
    return counts


# ── Attention required (spec §19) ──────────────────────────
def _attention(user, caps: set[str], counts: dict[str, int]) -> dict:
    blocks: list[dict] = []

    if Capability.CASES_VIEW in caps:
        open_cases = Case.objects.for_user(user).open()
        hp_cases = (
            open_cases.filter(priority__in=[CasePriority.HIGH, CasePriority.URGENT])
            .select_related("client", "assigned_lawyer")
            .order_by("-priority", "-updated_at")
        )
        blocks.append(
            _block(
                "high_priority_cases",
                "قضايا عالية الأولوية",
                "warning",
                hp_cases,
                lambda c: {
                    "text": f"{c.case_number} — {c.title}",
                    "when": None,
                    "badge": c.get_priority_display(),
                    "url": _url("cases:detail", args=[c.pk]),
                },
                _url("cases:list", query="priority=urgent"),
            )
        )

    if Capability.TASKS_VIEW in caps:
        od_tasks = overdue_tasks(user)
        od_deadlines = (
            Deadline.objects.for_user(user).overdue().select_related("case").order_by("due_date")
        )
        blocks.append(
            _block(
                "overdue_tasks",
                "مهام متأخرة",
                "danger",
                od_tasks,
                lambda t: {
                    "text": t.title,
                    "when": t.due_date,
                    "url": _url("tasks:detail", args=[t.pk]),
                },
                _url("tasks:list", query="overdue=on"),
                total=counts["overdue_tasks"],
            )
        )
        blocks.append(
            _block(
                "overdue_deadlines",
                "مواعيد نهائية فائتة",
                "danger",
                od_deadlines,
                lambda d: {
                    "text": d.title,
                    "when": d.due_date,
                    "url": _url("tasks:deadline_detail", args=[d.pk]),
                },
                _url("tasks:deadlines", query="overdue=on"),
            )
        )

    if Capability.HEARINGS_VIEW in caps:
        blocks.append(
            _block(
                "upcoming_hearings",
                f"جلسات خلال {ATTENTION_HEARING_DAYS} أيام",
                "warning",
                upcoming_hearings(user, days=ATTENTION_HEARING_DAYS),
                lambda h: {
                    "text": f"{h.case.case_number} — {h.get_hearing_type_display()}",
                    "when": h.scheduled_at,
                    "url": _url("hearings:detail", args=[h.pk]),
                },
                _url("hearings:list"),
            )
        )

    if Capability.CONTRACTS_VIEW in caps:
        blocks.append(
            _block(
                "expiring_contracts",
                "عقود قريبة من الانتهاء",
                "warning",
                expiring_contracts(user, days=EXPIRING_CONTRACT_DAYS),
                lambda c: {
                    "text": f"{c.contract_number} — {c.title}",
                    "when": c.end_date,
                    "url": _url("contracts:detail", args=[c.pk]),
                },
                _url("contracts:list", query="expiring=on"),
                total=counts["expiring_contracts"],
            )
        )

    if Capability.FINANCE_VIEW in caps:
        blocks.append(
            _block(
                "overdue_invoices",
                "فواتير متأخرة السداد",
                "danger",
                overdue_invoices(user),
                lambda i: {
                    "text": f"{i.invoice_number} — {i.client.display_name}",
                    "when": i.due_date,
                    "money": {"amount": i.outstanding, "currency": i.currency},
                    "url": _url("finance:invoice_detail", args=[i.pk]),
                },
                _url("finance:invoice_list", query="overdue=on"),
            )
        )

    shown = [b for b in blocks if b["count"]]
    return {"blocks": shown, "empty": not shown}


# ── KPIs (spec §18) ────────────────────────────────────────
def _kpi(key, label, value, url, *, tone="default"):
    return {
        "key": key,
        "label": label,
        "value": value,
        "url": url,
        "tone": tone if value else "default",
    }


def _kpis(user, caps: set[str], counts: dict) -> list[dict]:
    kpis: list[dict] = []
    if Capability.CASES_VIEW in caps:
        kpis.append(
            _kpi("active_cases", "القضايا النشطة", counts["active_cases"], _url("cases:list"))
        )
    if Capability.HEARINGS_VIEW in caps:
        kpis.append(
            _kpi("today_hearings", "جلسات اليوم", counts["today_hearings"], _url("agenda:day"))
        )
    if Capability.TASKS_VIEW in caps:
        kpis.append(
            _kpi(
                "overdue_tasks",
                "المهام المتأخرة",
                counts["overdue_tasks"],
                _url("tasks:list", query="overdue=on"),
                tone="danger",
            )
        )
    if Capability.CASES_VIEW in caps:
        kpis.append(
            _kpi(
                "urgent_cases",
                "القضايا العاجلة",
                counts["urgent_cases"],
                _url("cases:list", query="priority=urgent"),
                tone="warning",
            )
        )
    if Capability.CLIENTS_VIEW in caps:
        kpis.append(
            _kpi(
                "total_clients",
                "إجمالي العملاء",
                Client.objects.for_user(user).count(),
                _url("clients:list"),
            )
        )
    if Capability.CONTRACTS_VIEW in caps:
        kpis.append(
            _kpi(
                "expiring_contracts",
                "عقود قريبة من الانتهاء",
                counts["expiring_contracts"],
                _url("contracts:list", query="expiring=on"),
                tone="warning",
            )
        )
    if Capability.FINANCE_VIEW in caps:
        # Mixed currencies are never summed — the KPI is the *count* of open
        # invoices; per-currency amounts are in the Financial Overview.
        kpis.append(
            _kpi(
                "outstanding_invoices",
                "الفواتير المستحقة",
                outstanding_invoices(user).count(),
                _url("finance:invoice_list"),
                tone="warning",
            )
        )
    return kpis


# ── Today's hearings (spec §19) ────────────────────────────
def _today_hearings_rows(user) -> tuple[int, list[dict]]:
    """Bounded like every other list — the table shows the first `_LIST_LIMIT`;
    the true count feeds the 'جلسات اليوم' KPI and the calendar link covers the
    rest."""
    count, rows = _list(today_hearings(user))
    return count, [
        {
            "at": h.scheduled_at,
            "case_number": h.case.case_number,
            "client": h.case.client.display_name,
            "court": h.court.name if h.court_id else "",
            "lawyer": (h.lawyer.get_full_name() or h.lawyer.email) if h.lawyer_id else "",
            "type": h.get_hearing_type_display(),
            "status": h.get_status_display(),
            "url": _url("hearings:detail", args=[h.pk]),
        }
        for h in rows
    ]


# ── Case analytics (spec §19) ──────────────────────────────
def _breakdown(qs, field: str, labels: dict) -> list[dict]:
    return [
        {"label": labels.get(r[field], r[field] or "—"), "value": r["n"], "key": str(r[field])}
        for r in qs.values(field).annotate(n=Count("pk")).order_by("-n")
    ]


def _case_analytics(user, *, open_total: int) -> dict:
    scoped = Case.objects.for_user(user)
    open_scoped = scoped.open()

    by_lawyer = []
    for r in (
        open_scoped.values(
            "assigned_lawyer_id",
            "assigned_lawyer__first_name",
            "assigned_lawyer__last_name",
            "assigned_lawyer__email",
        )
        .annotate(n=Count("pk"))
        .order_by("-n")
    ):
        if r["assigned_lawyer_id"] is None:
            name = "غير مُسندة"
        else:
            name = (
                f"{r['assigned_lawyer__first_name']} {r['assigned_lawyer__last_name']}".strip()
                or r["assigned_lawyer__email"]
            )
        by_lawyer.append({"label": name, "value": r["n"], "key": str(r["assigned_lawyer_id"])})

    return {
        "total": scoped.count(),
        "open_total": open_total,
        "by_status": _breakdown(scoped, "status", dict(CaseStatus.choices)),
        "by_priority": _breakdown(open_scoped, "priority", dict(CasePriority.choices)),
        "by_type": _breakdown(open_scoped, "type__name", {}),
        "by_lawyer": by_lawyer,
    }


# ── Recent activity (spec §19) ─────────────────────────────
def _recent_activity(user, caps: set[str], *, limit: int = 12) -> list[dict]:
    actions: list[str] = []
    for cap, acts in _ACTIVITY_BY_CAP.items():
        if cap in caps:
            actions += list(acts)
    if not actions:
        return []
    qs = AuditLog.objects.filter(action__in=actions).select_related("actor")
    if Capability.CASES_VIEW_CONFIDENTIAL not in caps:
        qs = qs.exclude(action=AuditAction.CASE_CONFIDENTIAL_UPDATED)  # explicit + future-proof
    rows = []
    for log in qs.order_by("-created_at")[:limit]:
        name = _ENTITY_URL.get(log.entity_type)
        rows.append(
            {
                "label": log.action_label,
                "target": log.object_repr,
                "actor": (log.actor.get_full_name() or log.actor.email)
                if log.actor_id
                else "النظام",
                "at": log.created_at,
                "url": _url(name, args=[log.entity_id]) if (name and log.entity_id) else None,
            }
        )
    return rows


# ── Recently updated cases (spec §19) ──────────────────────
def _recent_cases(user) -> list[dict]:
    qs = (
        Case.objects.for_user(user)
        .open()
        .select_related("client")
        .order_by("-updated_at")[:_LIST_LIMIT]
    )
    return [
        {
            "case_number": c.case_number,
            "title": c.title,
            "client": c.client.display_name,
            "status": c.get_status_display(),
            "updated_at": c.updated_at,
            "url": _url("cases:detail", args=[c.pk]),
        }
        for c in qs
    ]


# ── the whole page ─────────────────────────────────────────
def build_dashboard(user) -> dict:
    from core.permissions.capabilities import capabilities_for

    caps = set(capabilities_for(user))
    has_cases = Capability.CASES_VIEW in caps
    has_tasks = Capability.TASKS_VIEW in caps
    has_hearings = Capability.HEARINGS_VIEW in caps
    fin_ok = Capability.FINANCE_VIEW in caps

    counts = _shared_counts(user, caps)
    attention_ctx = _attention(user, caps, counts)

    today_count, today_rows = _today_hearings_rows(user) if has_hearings else (0, [])
    counts["today_hearings"] = today_count

    ctx = {
        "kpis": _kpis(user, caps, counts),
        "today_hearings": today_rows,
        "show_today_hearings": has_hearings,
        "attention": attention_ctx,
        "upcoming_deadlines": (
            [
                {
                    "text": d.title,
                    "when": d.due_date,
                    "overdue": d.is_overdue,
                    "case": d.case.case_number if d.case_id else "",
                    "url": _url("tasks:deadline_detail", args=[d.pk]),
                }
                for d in upcoming_deadlines(user, days=DEADLINE_HORIZON_DAYS)[:10]
            ]
            if has_tasks
            else []
        ),
        "show_deadlines": has_tasks,
        "case_analytics": (
            _case_analytics(user, open_total=counts["active_cases"]) if has_cases else None
        ),
        "recent_cases": _recent_cases(user) if has_cases else [],
        "show_recent_cases": has_cases,
        "financial_overview": firm_financials(user, caps=caps),  # {"visible": fin_ok, ...}
        "recent_activity": _recent_activity(user, caps),
        "show_finance": fin_ok,
        "today": timezone.localdate(),
    }
    return ctx
