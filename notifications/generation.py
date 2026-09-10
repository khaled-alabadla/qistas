"""
The five Phase 11 reminder scans (spec §45, docs/adr/0035 §2–3, ADR-0005).

Each ``scan_*`` callable is idempotent: it derives a deterministic
``dedupe_key`` per (recipient, event, meaningful-date) and only creates rows
that do not already exist. Running the ``generate_notifications`` command twice
in a row creates nothing the second time.

**Authorization (spec Phase 11 §13–14):** recipients are the people who can act
on the event (the case team, the task assignee, the finance-responsible set),
then intersected with ``users_with_capability(<domain>.view)`` before any row is
written. ``invoice_overdue`` is gated on ``finance.view`` — a paralegal can
never receive or see it (docs/adr/0032). The stored ``url`` points at the domain
detail view, which enforces the same gate again.

No sensitive figures are put in a body (docs/adr/0009): invoice notifications
carry the number + due date, never the amount.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from contracts.models import Contract
from core.permissions.capabilities import Capability, users_with_capability
from hearings.models import Hearing, HearingStatus
from notifications.models import NotificationCategory
from notifications.services import NotificationSpec, bulk_notify
from tasks.models import Deadline, DeadlineStatus, Task

HEARING_WITHIN_DAYS = getattr(settings, "NOTIFY_HEARING_WITHIN_DAYS", 3)
DEADLINE_WITHIN_DAYS = getattr(settings, "NOTIFY_DEADLINE_WITHIN_DAYS", 7)
CONTRACT_WITHIN_DAYS = getattr(settings, "NOTIFY_CONTRACT_WITHIN_DAYS", 30)


def _iso(d: dt.date | dt.datetime) -> str:
    return d.isoformat()[:10]


def _capable_ids(capability: str) -> set[int]:
    return set(users_with_capability(capability).values_list("id", flat=True))


def _office_manager_ids() -> set[int]:
    from django.contrib.auth import get_user_model

    from core.permissions.capabilities import Group

    return set(
        get_user_model()
        ._default_manager.filter(is_active=True, groups__name=Group.OFFICE_MANAGER)
        .values_list("id", flat=True)
    )


def _case_team_ids(case) -> set[int]:
    """assigned lawyer + supporting lawyers of ``case``. Reads the
    ``supporting_lawyers`` prefetch cache — callers must
    ``prefetch_related("case__supporting_lawyers")`` to keep the scan flat."""
    ids: set[int] = set()
    if getattr(case, "assigned_lawyer_id", None):
        ids.add(case.assigned_lawyer_id)
    ids |= {u.id for u in case.supporting_lawyers.all()}
    return ids


def _emit(
    *,
    recipient_ids: Iterable[int],
    allowed_ids: set[int],
    category: str,
    title: str,
    body: str,
    dedupe_key: str,
    url: str,
    entity_type: str,
    entity_id,
) -> list[NotificationSpec]:
    specs: list[NotificationSpec] = []
    for rid in {r for r in recipient_ids if r in allowed_ids}:
        specs.append(
            NotificationSpec(
                recipient_id=rid,
                category=category,
                title=title,
                body=body,
                dedupe_key=dedupe_key,
                url=url,
                entity_type=entity_type,
                entity_id=str(entity_id),
            )
        )
    return specs


# ── Hearing approaching ────────────────────────────────────
def scan_upcoming_hearings(*, now=None, within_days: int | None = None) -> int:
    now = now or timezone.now()
    within = HEARING_WITHIN_DAYS if within_days is None else within_days
    allowed = _capable_ids(Capability.HEARINGS_VIEW)
    fallback = _office_manager_ids() & allowed
    horizon = now + dt.timedelta(days=within)

    hearings = (
        Hearing.objects.filter(
            status=HearingStatus.SCHEDULED,
            scheduled_at__gte=now,
            scheduled_at__lt=horizon,
        )
        .select_related("case", "case__client", "case__assigned_lawyer", "lawyer")
        .prefetch_related("case__supporting_lawyers")
    )
    specs: list[NotificationSpec] = []
    for h in hearings:
        recipients = _case_team_ids(h.case)
        if h.lawyer_id:
            recipients.add(h.lawyer_id)
        recipients &= allowed
        if not recipients:
            recipients = fallback
        local = timezone.localtime(h.scheduled_at)
        body = (
            f"جلسة قضية «{h.case.client.display_name}» "
            f"({h.case.case_number}) يوم {local:%Y-%m-%d} الساعة {local:%H:%M}."
        )
        specs += _emit(
            recipient_ids=recipients,
            allowed_ids=allowed,
            category=NotificationCategory.HEARING_UPCOMING,
            title="جلسة قادمة",
            body=body,
            dedupe_key=f"hearing_upcoming:{h.pk}:{_iso(local)}",
            url=reverse("hearings:detail", args=[h.pk]),
            entity_type="hearings.hearing",
            entity_id=h.pk,
        )
    return bulk_notify(specs)


# ── Task overdue ───────────────────────────────────────────
def scan_overdue_tasks(*, now=None) -> int:
    allowed = _capable_ids(Capability.TASKS_VIEW)
    fallback = _office_manager_ids() & allowed

    tasks = Task.objects.alive().overdue().select_related("assigned_to", "case", "client")
    specs: list[NotificationSpec] = []
    for t in tasks:
        recipients = {t.assigned_to_id} if t.assigned_to_id else set()
        recipients &= allowed
        if not recipients:
            recipients = fallback
        body = f"المهمة «{t.title}» تجاوزت تاريخ استحقاقها ({_iso(t.due_date)})."
        specs += _emit(
            recipient_ids=recipients,
            allowed_ids=allowed,
            category=NotificationCategory.TASK_OVERDUE,
            title="مهمة متأخرة",
            body=body,
            dedupe_key=f"task_overdue:{t.pk}:{_iso(t.due_date)}",
            url=reverse("tasks:detail", args=[t.pk]),
            entity_type="tasks.task",
            entity_id=t.pk,
        )
    return bulk_notify(specs)


# ── Deadline approaching (or already past) ─────────────────
def scan_approaching_deadlines(*, now=None, within_days: int | None = None) -> int:
    today = timezone.localtime(now).date() if now else timezone.localdate()
    within = DEADLINE_WITHIN_DAYS if within_days is None else within_days
    allowed = _capable_ids(Capability.TASKS_VIEW)
    fallback = _office_manager_ids() & allowed

    deadlines = (
        Deadline.objects.filter(
            status=DeadlineStatus.PENDING,
            due_date__lte=today + dt.timedelta(days=within),
        )
        .select_related("case", "case__client", "case__assigned_lawyer", "client")
        .prefetch_related("case__supporting_lawyers")
    )
    specs: list[NotificationSpec] = []
    for d in deadlines:
        recipients = _case_team_ids(d.case) if d.case_id else set()
        recipients &= allowed
        if not recipients:
            recipients = fallback
        if d.due_date < today:
            body = f"الموعد النهائي «{d.title}» فات في {_iso(d.due_date)}."
        else:
            body = f"الموعد النهائي «{d.title}» يستحق في {_iso(d.due_date)}."
        specs += _emit(
            recipient_ids=recipients,
            allowed_ids=allowed,
            category=NotificationCategory.DEADLINE_APPROACHING,
            title="موعد نهائي يقترب",
            body=body,
            dedupe_key=f"deadline_approaching:{d.pk}:{_iso(d.due_date)}",
            url=reverse("tasks:deadline_detail", args=[d.pk]),
            entity_type="tasks.deadline",
            entity_id=d.pk,
        )
    return bulk_notify(specs)


# ── Invoice overdue (finance.view only — docs/adr/0032) ────
def scan_overdue_invoices(*, now=None) -> int:
    from finance.models import Invoice

    allowed = _capable_ids(Capability.FINANCE_VIEW)
    if not allowed:
        return 0
    # The finance-responsible set: office manager + finance clerk.
    from django.contrib.auth import get_user_model

    from core.permissions.capabilities import Group

    responsible = (
        set(
            get_user_model()
            ._default_manager.filter(
                is_active=True,
                groups__name__in=[Group.OFFICE_MANAGER, Group.FINANCE_CLERK],
            )
            .values_list("id", flat=True)
        )
        & allowed
    )

    invoices = Invoice.objects.overdue().select_related("client")
    specs: list[NotificationSpec] = []
    for inv in invoices:
        # Body carries the number + client + due date — never the amount (§13).
        body = (
            f"الفاتورة {inv.invoice_number} للعميل «{inv.client.display_name}» "
            f"تجاوزت تاريخ الاستحقاق ({_iso(inv.due_date)})."
        )
        specs += _emit(
            recipient_ids=responsible,
            allowed_ids=allowed,
            category=NotificationCategory.INVOICE_OVERDUE,
            title="فاتورة متأخرة السداد",
            body=body,
            dedupe_key=f"invoice_overdue:{inv.pk}:{_iso(inv.due_date)}",
            url=reverse("finance:invoice_detail", args=[inv.pk]),
            entity_type="finance.invoice",
            entity_id=inv.pk,
        )
    return bulk_notify(specs)


# ── Contract expiring ─────────────────────────────────────
def scan_expiring_contracts(*, now=None, within_days: int | None = None) -> int:
    within = CONTRACT_WITHIN_DAYS if within_days is None else within_days
    allowed = _capable_ids(Capability.CONTRACTS_VIEW)
    fallback = _office_manager_ids() & allowed

    contracts = (
        Contract.objects.expiring_soon(within_days=within)
        .select_related("client", "case", "case__assigned_lawyer")
        .prefetch_related("case__supporting_lawyers")
    )
    specs: list[NotificationSpec] = []
    for c in contracts:
        recipients = _case_team_ids(c.case) if c.case_id else set()
        recipients &= allowed
        if not recipients:
            recipients = fallback
        body = f"العقد {c.contract_number} «{c.title}» ينتهي في {_iso(c.end_date)}."
        specs += _emit(
            recipient_ids=recipients,
            allowed_ids=allowed,
            category=NotificationCategory.CONTRACT_EXPIRING,
            title="عقد قريب من الانتهاء",
            body=body,
            dedupe_key=f"contract_expiring:{c.pk}:{_iso(c.end_date)}",
            url=reverse("contracts:detail", args=[c.pk]),
            entity_type="contracts.contract",
            entity_id=c.pk,
        )
    return bulk_notify(specs)


SCANS = {
    "hearing_upcoming": scan_upcoming_hearings,
    "task_overdue": scan_overdue_tasks,
    "deadline_approaching": scan_approaching_deadlines,
    "invoice_overdue": scan_overdue_invoices,
    "contract_expiring": scan_expiring_contracts,
}


def generate_all(*, now=None) -> dict[str, int]:
    """Run every scan. Returns ``{category: rows_created}``. Idempotent."""
    return {name: fn(now=now) for name, fn in SCANS.items()}
