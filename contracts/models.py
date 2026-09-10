"""
Contract — a legally significant engagement instrument tied to a client
(spec §37, §21, §33, docs/adr/0031).

* ``status`` carries the real lifecycle (``draft`` / ``active`` / ``expired`` /
  ``cancelled``) exactly per spec §37. ``cancelled`` is terminal.
* ``منتهي`` (expired) is a genuine status, flipped by the idempotent
  ``expire_contracts`` command (``contracts.services.expire_due_contracts``) —
  **not** stored automatically. Until it runs, ``is_past_due`` / ``expiring_soon``
  close the gap in the UI (docs/adr/0006).
* A contract is never deleted (docs/adr/0022 — same class as ``Hearing`` /
  ``Deadline``): ``default_permissions = ("add", "change", "view")``.
* ``value`` is a single stored amount — informational, no arithmetic. Finance
  (invoicing, roll-ups) is Phase 8 and builds on top additively.
"""

from __future__ import annotations

import datetime as dt

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import AuthoredModel, TimeStampedModel
from core.querysets import ScopedManager, ScopedQuerySet

EXPIRING_SOON_DAYS = 30

# ── Enumerations ───────────────────────────────────────────


class ContractStatus(models.TextChoices):
    DRAFT = "draft", _("مسودة")
    ACTIVE = "active", _("ساري")
    EXPIRED = "expired", _("منتهي")
    CANCELLED = "cancelled", _("ملغى")


class ContractType(models.TextChoices):
    RETAINER = "retainer", _("اتفاقية أتعاب دورية")
    ENGAGEMENT = "engagement", _("اتفاقية تمثيل قانوني")
    SERVICES = "services", _("عقد خدمات")
    CONSULTING = "consulting", _("عقد استشارات")
    LEASE = "lease", _("عقد إيجار")
    EMPLOYMENT = "employment", _("عقد عمل")
    NDA = "nda", _("اتفاقية سرية")
    SETTLEMENT = "settlement", _("اتفاقية تسوية")
    OTHER = "other", _("أخرى")


class Currency(models.TextChoices):
    ILS = "ILS", _("شيكل")
    JOD = "JOD", _("دينار أردني")
    USD = "USD", _("دولار أمريكي")
    EUR = "EUR", _("يورو")


# Statuses for which "past due" / "expiring soon" are meaningful.
CONTRACT_CLOSED = {ContractStatus.EXPIRED, ContractStatus.CANCELLED}

# `notes` and `value` are deliberately excluded (spec §4 — not unnecessarily
# searchable / indexed).
SEARCH_FIELDS = ("contract_number", "title", "description")


# ── Contract ───────────────────────────────────────────────
class ContractQuerySet(ScopedQuerySet):
    def for_user(self, user) -> ContractQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        return self.all_for_user()  # all staff see all (docs/adr/0008)

    def active(self) -> ContractQuerySet:
        return self.filter(status=ContractStatus.ACTIVE)

    def open(self) -> ContractQuerySet:
        return self.exclude(status__in=list(CONTRACT_CLOSED))

    def past_due(self) -> ContractQuerySet:
        """``active`` contracts whose ``end_date`` is already in the past."""
        return self.filter(
            status=ContractStatus.ACTIVE,
            end_date__isnull=False,
            end_date__lt=timezone.localdate(),
        )

    def expiring_soon(self, within_days: int = EXPIRING_SOON_DAYS) -> ContractQuerySet:
        """``active`` contracts whose ``end_date`` falls within the next
        ``within_days`` days (today .. today+N inclusive)."""
        today = timezone.localdate()
        return self.filter(
            status=ContractStatus.ACTIVE,
            end_date__isnull=False,
            end_date__gte=today,
            end_date__lte=today + dt.timedelta(days=within_days),
        )

    def search(self, term: str) -> ContractQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Contract(TimeStampedModel, AuthoredModel):
    contract_number = models.CharField(_("رقم العقد"), max_length=20, unique=True, editable=False)
    title = models.CharField(_("العنوان"), max_length=250)
    contract_type = models.CharField(
        _("نوع العقد"),
        max_length=20,
        choices=ContractType.choices,
        default=ContractType.ENGAGEMENT,
    )

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="contracts",
        verbose_name=_("الموكل"),
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts",
        verbose_name=_("القضية"),
    )

    start_date = models.DateField(_("تاريخ البدء"))
    end_date = models.DateField(_("تاريخ الانتهاء"), null=True, blank=True)

    value = models.DecimalField(_("القيمة"), max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(
        _("العملة"), max_length=3, choices=Currency.choices, default=Currency.ILS
    )

    status = models.CharField(
        _("الحالة"),
        max_length=15,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
    )
    description = models.TextField(_("الوصف"), blank=True)
    notes = models.TextField(_("ملاحظات"), blank=True)

    objects = ScopedManager.from_queryset(ContractQuerySet)()

    class Meta:
        verbose_name = _("عقد")
        verbose_name_plural = _("العقود")
        ordering = ("-created_at",)
        default_permissions = ("add", "change", "view")  # never deleted (docs/adr/0022)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["contract_type"]),
            models.Index(fields=["end_date"]),
            models.Index(fields=["client"]),
            models.Index(fields=["case"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="contract_value_non_negative",
                condition=Q(value__isnull=True) | Q(value__gte=0),
            ),
            models.CheckConstraint(
                name="contract_end_after_start",
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.contract_number} — {self.title}"

    def clean(self) -> None:
        super().clean()
        from django.core.exceptions import ValidationError

        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("تاريخ الانتهاء يسبق تاريخ البدء.")})
        if self.value is not None and self.value < 0:
            raise ValidationError({"value": _("القيمة لا يمكن أن تكون سالبة.")})

    # ── computed lifecycle flags (docs/adr/0006 — never stored) ─────────
    @property
    def is_open(self) -> bool:
        return self.status not in CONTRACT_CLOSED

    @property
    def days_until_expiry(self) -> int | None:
        if not self.end_date:
            return None
        return (self.end_date - timezone.localdate()).days

    @property
    def is_past_due(self) -> bool:
        """An ``active`` contract whose end date has already passed but whose
        status has not been flipped to ``expired`` yet."""
        return bool(
            self.status == ContractStatus.ACTIVE
            and self.end_date
            and self.end_date < timezone.localdate()
        )

    @property
    def is_expiring_soon(self) -> bool:
        days = self.days_until_expiry
        return bool(
            self.status == ContractStatus.ACTIVE
            and days is not None
            and 0 <= days <= EXPIRING_SOON_DAYS
        )
