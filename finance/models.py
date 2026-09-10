"""
Finance domain — fee agreements, invoices, payments, credit notes, expenses
(spec §37–42, §21, §97, §98; docs/adr/0011, 0012, 0013, 0032).

Money rules (§42):
* every amount is ``Decimal`` — **never** ``float``;
* every stored monetary result goes through ``core.money.quantize`` (2 dp,
  ``ROUND_HALF_UP``);
* all arithmetic is server-side, in ``finance.services`` — never a form field.

Immutability (ADR-0012):
* an **issued** invoice's line items + monetary fields are frozen — no code path
  mutates them; corrections are a ``CreditNote``;
* ``Payment`` and ``PaymentReversal`` and ``CreditNote`` are append-only
  (``default_permissions`` without ``change`` / ``delete``).

No finance row is ever hard-deleted (ADR-0022).
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import AuthoredModel, TimeStampedModel
from core.money import ZERO, Currency
from core.querysets import ScopedManager, ScopedQuerySet

# ── Enumerations ───────────────────────────────────────────


class FeeType(models.TextChoices):
    FIXED = "fixed", _("مقطوع")
    HOURLY = "hourly", _("بالساعة")
    CONTINGENCY = "contingency", _("نسبة من المحصّل")
    RETAINER = "retainer", _("أتعاب دورية")


class FeeAgreementStatus(models.TextChoices):
    DRAFT = "draft", _("مسودة")
    ACTIVE = "active", _("سارية")
    COMPLETED = "completed", _("منجزة")
    CANCELLED = "cancelled", _("ملغاة")


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", _("مسودة")
    UNPAID = "unpaid", _("غير مدفوعة")
    PARTIALLY_PAID = "partially_paid", _("مدفوعة جزئيًا")
    PAID = "paid", _("مدفوعة")
    CANCELLED = "cancelled", _("ملغاة")


class PaymentMethod(models.TextChoices):
    CASH = "cash", _("نقدًا")
    BANK_TRANSFER = "bank_transfer", _("تحويل بنكي")
    CHEQUE = "cheque", _("شيك")
    CARD = "card", _("بطاقة")
    OTHER = "other", _("أخرى")


class ExpenseCategory(models.TextChoices):
    COURT_FEES = "court_fees", _("رسوم محكمة")
    GOVERNMENT_FEES = "government_fees", _("رسوم حكومية")
    EXPERT_FEES = "expert_fees", _("أتعاب خبراء")
    TRAVEL = "travel", _("سفر وتنقّل")
    OFFICE = "office", _("مصاريف مكتب")
    TRANSLATION = "translation", _("ترجمة")
    OTHER = "other", _("أخرى")


INVOICE_OPEN_STATUSES = {InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID}
INVOICE_ISSUED_STATUSES = {
    InvoiceStatus.UNPAID,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.PAID,
}

FEE_AGREEMENT_SEARCH_FIELDS = ("reference", "description")
INVOICE_SEARCH_FIELDS = ("invoice_number", "notes")
EXPENSE_SEARCH_FIELDS = ("reference", "description")


def _authed_or_none(qs, user):
    if not user or not user.is_authenticated:
        return qs.none()._scoped_copy()
    return qs.all_for_user()  # capability gate is in the view (docs/adr/0008)


# ── FeeAgreement ───────────────────────────────────────────
class FeeAgreementQuerySet(ScopedQuerySet):
    def for_user(self, user) -> FeeAgreementQuerySet:
        return _authed_or_none(self, user)

    def active(self) -> FeeAgreementQuerySet:
        return self.filter(status=FeeAgreementStatus.ACTIVE)

    def search(self, term: str) -> FeeAgreementQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in FEE_AGREEMENT_SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class FeeAgreement(TimeStampedModel, AuthoredModel):
    reference = models.CharField(_("المرجع"), max_length=20, unique=True, editable=False)
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.PROTECT,
        related_name="fee_agreements",
        verbose_name=_("القضية"),
    )
    fee_type = models.CharField(
        _("نوع الأتعاب"), max_length=15, choices=FeeType.choices, default=FeeType.FIXED
    )
    fixed_amount = models.DecimalField(
        _("المبلغ المقطوع"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    hourly_rate = models.DecimalField(
        _("سعر الساعة"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    contingency_percent = models.DecimalField(
        _("النسبة %"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(
        _("العملة"), max_length=3, choices=Currency.choices, default=Currency.ILS
    )
    status = models.CharField(
        _("الحالة"),
        max_length=15,
        choices=FeeAgreementStatus.choices,
        default=FeeAgreementStatus.DRAFT,
    )
    agreed_on = models.DateField(_("تاريخ الاتفاق"), null=True, blank=True)
    start_date = models.DateField(_("تاريخ البدء"), null=True, blank=True)
    end_date = models.DateField(_("تاريخ الانتهاء"), null=True, blank=True)
    description = models.TextField(_("الوصف"), blank=True)
    notes = models.TextField(_("ملاحظات"), blank=True)

    objects = ScopedManager.from_queryset(FeeAgreementQuerySet)()

    class Meta:
        verbose_name = _("اتفاقية أتعاب")
        verbose_name_plural = _("اتفاقيات الأتعاب")
        ordering = ("-created_at",)
        default_permissions = ("add", "change", "view")  # never deleted (ADR-0022)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["fee_type"]),
            models.Index(fields=["case"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="fee_fixed_amount_non_negative",
                condition=Q(fixed_amount__isnull=True) | Q(fixed_amount__gte=0),
            ),
            models.CheckConstraint(
                name="fee_hourly_rate_non_negative",
                condition=Q(hourly_rate__isnull=True) | Q(hourly_rate__gte=0),
            ),
            models.CheckConstraint(
                name="fee_contingency_percent_range",
                condition=Q(contingency_percent__isnull=True)
                | Q(contingency_percent__gte=0, contingency_percent__lte=100),
            ),
            models.CheckConstraint(
                name="fee_end_after_start",
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.get_fee_type_display()}"

    def clean(self) -> None:
        super().clean()
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}
        if self.fee_type == FeeType.HOURLY:
            if self.hourly_rate is None:
                errors["hourly_rate"] = _("مطلوب لنوع الأتعاب «بالساعة».")
        elif self.fee_type == FeeType.CONTINGENCY:
            if self.contingency_percent is None:
                errors["contingency_percent"] = _("مطلوب لنوع الأتعاب «نسبة من المحصّل».")
        elif self.fixed_amount is None:  # fixed / retainer
            errors["fixed_amount"] = _("مطلوب لهذا النوع من الأتعاب.")
        if self.contingency_percent is not None and not (0 <= self.contingency_percent <= 100):
            errors["contingency_percent"] = _("النسبة بين 0 و 100.")
        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = _("تاريخ الانتهاء يسبق تاريخ البدء.")
        if errors:
            raise ValidationError(errors)

    @property
    def is_open(self) -> bool:
        return self.status not in {FeeAgreementStatus.COMPLETED, FeeAgreementStatus.CANCELLED}

    @property
    def headline_amount(self):
        """The figure to show in a list / badge, or ``None``."""
        if self.fee_type == FeeType.HOURLY:
            return self.hourly_rate
        if self.fee_type == FeeType.CONTINGENCY:
            return None
        return self.fixed_amount


# ── Invoice ────────────────────────────────────────────────
class InvoiceQuerySet(ScopedQuerySet):
    def for_user(self, user) -> InvoiceQuerySet:
        return _authed_or_none(self, user)

    def issued(self) -> InvoiceQuerySet:
        return self.filter(status__in=list(INVOICE_ISSUED_STATUSES))

    def open(self) -> InvoiceQuerySet:
        return self.filter(status__in=list(INVOICE_OPEN_STATUSES))

    def overdue(self) -> InvoiceQuerySet:
        return self.filter(
            status__in=list(INVOICE_OPEN_STATUSES),
            due_date__isnull=False,
            due_date__lt=timezone.localdate(),
        )

    def search(self, term: str) -> InvoiceQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in INVOICE_SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)

    def with_balances(self) -> InvoiceQuerySet:
        """Annotate ``_credited_sum`` so ``credited_total`` / ``outstanding`` need
        no per-row query. Use on every list / card / calendar queryset."""
        from django.db.models import DecimalField
        from django.db.models.functions import Coalesce

        return self.annotate(
            _credited_sum=Coalesce(
                models.Sum("credit_notes__amount"),
                models.Value(ZERO, output_field=DecimalField(max_digits=16, decimal_places=2)),
            )
        )


class Invoice(TimeStampedModel, AuthoredModel):
    invoice_number = models.CharField(
        _("رقم الفاتورة"), max_length=20, unique=True, null=True, blank=True, editable=False
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("الموكل"),
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name=_("القضية"),
    )
    fee_agreement = models.ForeignKey(
        "finance.FeeAgreement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name=_("اتفاقية الأتعاب"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=15,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
    )
    issue_date = models.DateField(_("تاريخ الإصدار"), null=True, blank=True)
    due_date = models.DateField(_("تاريخ الاستحقاق"), null=True, blank=True)
    currency = models.CharField(
        _("العملة"), max_length=3, choices=Currency.choices, default=Currency.ILS
    )

    # Inputs (editable while draft).
    discount = models.DecimalField(_("الخصم"), max_digits=14, decimal_places=2, default=ZERO)
    tax_rate = models.DecimalField(
        _("نسبة الضريبة %"), max_digits=5, decimal_places=2, default=ZERO
    )
    # Server-computed snapshots — frozen at issue (ADR-0012). Never a form field.
    subtotal = models.DecimalField(
        _("المجموع الفرعي"), max_digits=14, decimal_places=2, default=ZERO, editable=False
    )
    tax_amount = models.DecimalField(
        _("قيمة الضريبة"), max_digits=14, decimal_places=2, default=ZERO, editable=False
    )
    total = models.DecimalField(
        _("الإجمالي"), max_digits=14, decimal_places=2, default=ZERO, editable=False
    )
    amount_paid = models.DecimalField(
        _("المدفوع"), max_digits=14, decimal_places=2, default=ZERO, editable=False
    )

    notes = models.TextField(_("ملاحظات"), blank=True)

    objects = ScopedManager.from_queryset(InvoiceQuerySet)()

    class Meta:
        verbose_name = _("فاتورة")
        verbose_name_plural = _("الفواتير")
        ordering = ("-created_at",)
        default_permissions = ("add", "change", "view")  # issued = immutable (ADR-0012)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["client"]),
            models.Index(fields=["case"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="invoice_discount_non_negative", condition=Q(discount__gte=0)
            ),
            models.CheckConstraint(
                name="invoice_tax_rate_range", condition=Q(tax_rate__gte=0, tax_rate__lte=100)
            ),
            models.CheckConstraint(
                name="invoice_subtotal_non_negative", condition=Q(subtotal__gte=0)
            ),
            models.CheckConstraint(
                name="invoice_tax_amount_non_negative", condition=Q(tax_amount__gte=0)
            ),
            models.CheckConstraint(name="invoice_total_non_negative", condition=Q(total__gte=0)),
            models.CheckConstraint(
                name="invoice_amount_paid_non_negative", condition=Q(amount_paid__gte=0)
            ),
            models.CheckConstraint(
                name="invoice_no_overpayment",
                condition=Q(amount_paid__lte=models.F("total")),
            ),
        ]

    def __str__(self) -> str:
        return self.invoice_number or _("فاتورة مسودة #%(pk)s") % {"pk": self.pk}

    def clean(self) -> None:
        super().clean()
        from django.core.exceptions import ValidationError

        if self.discount is not None and self.discount < 0:
            raise ValidationError({"discount": _("الخصم لا يمكن أن يكون سالبًا.")})
        if self.tax_rate is not None and not (0 <= self.tax_rate <= 100):
            raise ValidationError({"tax_rate": _("نسبة الضريبة بين 0 و 100.")})

    # ── lifecycle helpers ──────────────────────────────────
    @property
    def is_draft(self) -> bool:
        return self.status == InvoiceStatus.DRAFT

    @property
    def is_issued(self) -> bool:
        return self.status in INVOICE_ISSUED_STATUSES

    @property
    def is_editable(self) -> bool:
        """Only a draft's content may change (ADR-0012)."""
        return self.status == InvoiceStatus.DRAFT

    @property
    def total_credited(self):
        """Σ credit notes. Uses the ``with_balances()`` annotation or the
        prefetch cache when present, else one aggregate query."""
        from core.money import quantize

        if hasattr(self, "_credited_sum"):
            return quantize(self._credited_sum or ZERO)
        cache = getattr(self, "_prefetched_objects_cache", {})
        if "credit_notes" in cache:
            return quantize(sum((cn.amount for cn in cache["credit_notes"]), ZERO))
        return quantize(self.credit_notes.aggregate(s=models.Sum("amount"))["s"] or ZERO)

    @property
    def credited_total(self):
        """``total`` minus every credit note — what the client is expected to pay."""
        from core.money import quantize

        return quantize(self.total - self.total_credited)

    @property
    def outstanding(self):
        from core.money import quantize

        return quantize(max(self.credited_total - self.amount_paid, ZERO))

    @property
    def is_overdue(self) -> bool:
        """Computed — never stored (ADR-0006). Overdue-ness flips back the moment
        the invoice is paid, so it is a property, not a lifecycle status."""
        return bool(
            self.status in INVOICE_OPEN_STATUSES
            and self.due_date
            and self.due_date < timezone.localdate()
        )

    @property
    def days_overdue(self) -> int:
        if not (self.is_overdue and self.due_date):
            return 0
        return (timezone.localdate() - self.due_date).days


class InvoiceLineItem(TimeStampedModel):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="line_items", verbose_name=_("الفاتورة")
    )
    description = models.CharField(_("البند"), max_length=300)
    quantity = models.DecimalField(_("الكمية"), max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(_("سعر الوحدة"), max_digits=14, decimal_places=2)
    line_total = models.DecimalField(
        _("إجمالي البند"), max_digits=14, decimal_places=2, default=ZERO, editable=False
    )
    position = models.PositiveIntegerField(_("الترتيب"), default=0)

    class Meta:
        verbose_name = _("بند فاتورة")
        verbose_name_plural = _("بنود الفاتورة")
        ordering = ("position", "pk")
        default_permissions = ("add", "change", "view")
        constraints = [
            models.CheckConstraint(name="line_quantity_positive", condition=Q(quantity__gt=0)),
            models.CheckConstraint(
                name="line_unit_price_non_negative", condition=Q(unit_price__gte=0)
            ),
            models.CheckConstraint(name="line_total_non_negative", condition=Q(line_total__gte=0)),
        ]

    def __str__(self) -> str:
        return self.description

    def compute_total(self):
        from core.money import quantize

        return quantize(self.quantity * self.unit_price)


# ── Payment ────────────────────────────────────────────────
class PaymentQuerySet(ScopedQuerySet):
    def for_user(self, user) -> PaymentQuerySet:
        return _authed_or_none(self, user)


class Payment(TimeStampedModel, AuthoredModel):
    reference = models.CharField(_("مرجع الدفعة"), max_length=20, unique=True, editable=False)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments", verbose_name=_("الفاتورة")
    )
    amount = models.DecimalField(_("المبلغ"), max_digits=14, decimal_places=2)
    paid_on = models.DateField(_("تاريخ الدفع"))
    method = models.CharField(
        _("طريقة الدفع"), max_length=15, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    external_reference = models.CharField(_("مرجع خارجي"), max_length=100, blank=True)
    note = models.TextField(_("ملاحظات"), blank=True)

    objects = ScopedManager.from_queryset(PaymentQuerySet)()

    class Meta:
        verbose_name = _("دفعة")
        verbose_name_plural = _("المدفوعات")
        ordering = ("-paid_on", "-created_at")
        default_permissions = ("add", "view")  # immutable (ADR-0012)
        indexes = [
            models.Index(fields=["invoice"]),
            models.Index(fields=["-paid_on"]),
        ]
        constraints = [
            models.CheckConstraint(name="payment_amount_positive", condition=Q(amount__gt=0)),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.amount}"

    @property
    def reversed_amount(self):
        from core.money import quantize

        cache = getattr(self, "_prefetched_objects_cache", {})
        if "reversals" in cache:
            return quantize(sum((r.amount for r in cache["reversals"]), ZERO))
        s = self.reversals.aggregate(s=models.Sum("amount"))["s"] or ZERO
        return quantize(s)

    @property
    def net_amount(self):
        from core.money import quantize

        return quantize(self.amount - self.reversed_amount)


class PaymentReversal(TimeStampedModel, AuthoredModel):
    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="reversals", verbose_name=_("الدفعة")
    )
    amount = models.DecimalField(_("المبلغ"), max_digits=14, decimal_places=2)
    reason = models.TextField(_("السبب"))
    reversed_on = models.DateField(_("تاريخ الاسترجاع"), default=dt.date.today)

    objects = models.Manager()

    class Meta:
        verbose_name = _("استرجاع دفعة")
        verbose_name_plural = _("استرجاعات الدفعات")
        ordering = ("-created_at",)
        default_permissions = ("add", "view")  # immutable
        constraints = [
            models.CheckConstraint(name="reversal_amount_positive", condition=Q(amount__gt=0)),
        ]

    def __str__(self) -> str:
        return f"{self.payment.reference} ⟲ {self.amount}"


# ── CreditNote ─────────────────────────────────────────────
class CreditNote(TimeStampedModel, AuthoredModel):
    credit_number = models.CharField(
        _("رقم الإشعار الدائن"), max_length=20, unique=True, editable=False
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="credit_notes", verbose_name=_("الفاتورة")
    )
    amount = models.DecimalField(_("المبلغ"), max_digits=14, decimal_places=2)
    reason = models.TextField(_("السبب"))
    issued_on = models.DateField(_("تاريخ الإصدار"), default=dt.date.today)

    objects = models.Manager()

    class Meta:
        verbose_name = _("إشعار دائن")
        verbose_name_plural = _("الإشعارات الدائنة")
        ordering = ("-created_at",)
        default_permissions = ("add", "view")  # immutable (ADR-0012)
        indexes = [models.Index(fields=["invoice"])]
        constraints = [
            models.CheckConstraint(name="credit_note_amount_positive", condition=Q(amount__gt=0)),
        ]

    def __str__(self) -> str:
        return f"{self.credit_number} — {self.amount}"


# ── Expense ────────────────────────────────────────────────
class ExpenseQuerySet(ScopedQuerySet):
    def for_user(self, user) -> ExpenseQuerySet:
        return _authed_or_none(self, user)

    def alive(self) -> ExpenseQuerySet:
        return self.filter(deleted_at__isnull=True)

    def search(self, term: str) -> ExpenseQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in EXPENSE_SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Expense(TimeStampedModel, AuthoredModel):
    reference = models.CharField(_("المرجع"), max_length=20, unique=True, editable=False)
    description = models.CharField(_("الوصف"), max_length=300)
    amount = models.DecimalField(_("المبلغ"), max_digits=14, decimal_places=2)
    currency = models.CharField(
        _("العملة"), max_length=3, choices=Currency.choices, default=Currency.ILS
    )
    category = models.CharField(
        _("التصنيف"),
        max_length=20,
        choices=ExpenseCategory.choices,
        default=ExpenseCategory.OTHER,
    )
    spent_on = models.DateField(_("تاريخ الصرف"))
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
        verbose_name=_("القضية"),
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
        verbose_name=_("الموكل"),
    )
    note = models.TextField(_("ملاحظات"), blank=True)

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    objects = ScopedManager.from_queryset(ExpenseQuerySet)()

    class Meta:
        verbose_name = _("مصروف")
        verbose_name_plural = _("المصروفات")
        ordering = ("-spent_on", "-created_at")
        default_permissions = ("add", "change", "view")  # soft-delete only (ADR-0022)
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["case"]),
            models.Index(fields=["client"]),
            models.Index(fields=["-spent_on"]),
            models.Index(fields=["deleted_at"]),
        ]
        constraints = [
            models.CheckConstraint(name="expense_amount_positive", condition=Q(amount__gt=0)),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.description}"

    @property
    def is_retired(self) -> bool:
        return self.deleted_at is not None
