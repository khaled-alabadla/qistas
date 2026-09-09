"""
Case — the central domain object (spec §22–27).

Visibility (docs/adr/0008): every authenticated staff member sees every case in
lists and detail; **editing** is capability-gated. `legal_notes` / `internal_notes`
live on a separate `CaseConfidential` 1:1 row behind `cases.view_confidential`
(docs/adr/0008, 0009) so they can never leak into a list, an export, or an audit
diff by accident. Closing a case is a status change, never a delete (docs/adr/0022).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import AuthoredModel, TimeStampedModel
from core.querysets import ScopedManager, ScopedQuerySet

# ── Enumerations (spec §23–25) ──────────────────────────────

DEFAULT_CASE_TYPES = [
    "مدنية",
    "تجارية",
    "عمالية",
    "جزائية",
    "أحوال شخصية",
    "إدارية",
    "أخرى",
]


class CaseStatus(models.TextChoices):
    NEW = "new", _("جديدة")
    IN_PROGRESS = "in_progress", _("قيد المتابعة")
    IN_TRIAL = "in_trial", _("قيد المحاكمة")
    ON_HOLD = "on_hold", _("معلقة")
    CONCLUDED = "concluded", _("منتهية")
    CLOSED = "closed", _("مغلقة")


TERMINAL_STATUSES = {CaseStatus.CONCLUDED, CaseStatus.CLOSED}


class CasePriority(models.TextChoices):
    LOW = "low", _("منخفضة")
    MEDIUM = "medium", _("متوسطة")
    HIGH = "high", _("عالية")
    URGENT = "urgent", _("عاجلة")


class PartyRole(models.TextChoices):
    CLIENT = "client", _("عميل")
    OPPONENT = "opponent", _("طرف مقابل")
    COUNSEL = "counsel", _("محامٍ")
    REPRESENTATIVE = "representative", _("ممثل")
    OTHER = "other", _("جهة أخرى")


class NoteKind(models.TextChoices):
    GENERAL = "general", _("ملاحظة")
    CORRESPONDENCE = "correspondence", _("مراسلة")


SEARCH_FIELDS = (
    "case_number",
    "title",
    "court_case_number",
    "internal_reference",
    "department",
)


# ── Case type (configurable table — spec §23) ───────────────
class CaseType(models.Model):
    name = models.CharField(_("النوع"), max_length=100, unique=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    order = models.PositiveSmallIntegerField(_("الترتيب"), default=0)

    class Meta:
        verbose_name = _("نوع قضية")
        verbose_name_plural = _("أنواع القضايا")
        ordering = ("order", "name")

    def __str__(self) -> str:
        return self.name


# ── Case ───────────────────────────────────────────────────
class CaseQuerySet(ScopedQuerySet):
    def for_user(self, user) -> CaseQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        return self.all_for_user()  # no per-row siloing in v1 (docs/adr/0008)

    def open(self) -> CaseQuerySet:
        return self.exclude(status__in=list(TERMINAL_STATUSES))

    def search(self, term: str) -> CaseQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Case(TimeStampedModel, AuthoredModel):
    case_number = models.CharField(_("رقم القضية"), max_length=30, unique=True, editable=False)
    internal_reference = models.CharField(_("مرجع داخلي"), max_length=60, blank=True)
    court_case_number = models.CharField(
        _("رقم القضية لدى المحكمة"), max_length=60, blank=True, db_index=True
    )
    title = models.CharField(_("العنوان"), max_length=250)

    type = models.ForeignKey(
        CaseType, on_delete=models.PROTECT, related_name="cases", verbose_name=_("النوع")
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="cases",
        verbose_name=_("الموكل"),
    )
    assigned_lawyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_cases",
        verbose_name=_("المحامي المسؤول"),
    )
    supporting_lawyers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CaseLawyer",
        through_fields=("case", "lawyer"),
        related_name="supporting_cases",
        blank=True,
        verbose_name=_("محامون مساندون"),
    )
    court = models.ForeignKey(
        "courts.Court",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cases",
        verbose_name=_("المحكمة"),
    )
    department = models.CharField(_("الدائرة"), max_length=120, blank=True)

    status = models.CharField(
        _("الحالة"), max_length=20, choices=CaseStatus.choices, default=CaseStatus.NEW
    )
    stage = models.CharField(_("المرحلة"), max_length=120, blank=True)
    priority = models.CharField(
        _("الأولوية"),
        max_length=10,
        choices=CasePriority.choices,
        default=CasePriority.MEDIUM,
    )
    filing_date = models.DateField(_("تاريخ التقديم"), null=True, blank=True)
    claim_amount = models.DecimalField(
        _("قيمة المطالبة"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    description = models.TextField(_("الوصف"), blank=True)

    objects = ScopedManager.from_queryset(CaseQuerySet)()

    class Meta:
        verbose_name = _("قضية")
        verbose_name_plural = _("القضايا")
        ordering = ("-created_at",)
        permissions = [
            ("view_confidential_case", _("عرض الملاحظات القانونية والداخلية للقضية")),
        ]
        indexes = [
            models.Index(fields=["case_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["type"]),
            models.Index(fields=["client"]),
            models.Index(fields=["assigned_lawyer"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["filing_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="case_claim_amount_non_negative",
                condition=Q(claim_amount__isnull=True) | Q(claim_amount__gte=0),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.case_number} — {self.title}"

    @property
    def is_open(self) -> bool:
        return self.status not in TERMINAL_STATUSES

    @property
    def is_closed(self) -> bool:
        return self.status == CaseStatus.CLOSED

    @property
    def next_hearing(self):
        """The soonest still-scheduled future hearing (spec §22/§26). **Derived**,
        never stored — rescheduling / cancelling / completing a hearing changes
        the answer for free (docs/adr/0028)."""
        from django.utils import timezone

        from hearings.models import HearingStatus

        return (
            self.hearings.filter(status=HearingStatus.SCHEDULED, scheduled_at__gte=timezone.now())
            .select_related("court")
            .order_by("scheduled_at")
            .first()
        )

    def get_confidential(self) -> CaseConfidential:
        """Row for writing — creates it if absent. Never call this on a GET/read
        path (it writes a row + an auditlog 'created' event); use
        ``confidential_or_none`` there."""
        obj, _created = CaseConfidential.objects.get_or_create(case=self)
        return obj

    def confidential_or_none(self) -> CaseConfidential | None:
        return CaseConfidential.objects.filter(case=self).first()


class CaseConfidential(models.Model):
    """Privileged notes, isolated so an unqualified query cannot select them."""

    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name="confidential")
    legal_notes = models.TextField(_("ملاحظات قانونية"), blank=True)
    internal_notes = models.TextField(_("ملاحظات داخلية"), blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("ملاحظات سرية للقضية")
        verbose_name_plural = _("ملاحظات سرية للقضايا")

    def __str__(self) -> str:
        return f"سري: {self.case.case_number}"

    @property
    def is_empty(self) -> bool:
        return not (self.legal_notes.strip() or self.internal_notes.strip())


class CaseLawyer(models.Model):
    """Through model for `Case.supporting_lawyers`."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="lawyer_links")
    lawyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="case_links"
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["case", "lawyer"], name="caselawyer_uniq")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.case.case_number} · {self.lawyer}"


class CaseParty(models.Model):
    """A party to the case other than the primary client / office lawyers
    (spec §27 — a relationship model, not a single opposing party)."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="parties")
    party_role = models.CharField(
        _("الصفة"), max_length=20, choices=PartyRole.choices, default=PartyRole.OPPONENT
    )
    name = models.CharField(_("الاسم"), max_length=200)
    phone = models.CharField(_("الهاتف"), max_length=30, blank=True)
    email = models.EmailField(_("البريد الإلكتروني"), blank=True)
    notes = models.CharField(_("ملاحظات"), max_length=300, blank=True)
    linked_client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="case_party_links",
        verbose_name=_("عميل مرتبط"),
    )
    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("طرف")
        verbose_name_plural = _("الأطراف")
        ordering = ("party_role", "name")

    def __str__(self) -> str:
        return f"{self.get_party_role_display()}: {self.name}"


class CaseNote(TimeStampedModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="notes")
    kind = models.CharField(
        _("النوع"), max_length=20, choices=NoteKind.choices, default=NoteKind.GENERAL
    )
    body = models.TextField(_("النص"))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("ملاحظة قضية")
        verbose_name_plural = _("ملاحظات القضايا")
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.get_kind_display()} · {self.case.case_number}"


class CaseEventType(models.TextChoices):
    CREATED = "created", _("إنشاء القضية")
    UPDATED = "updated", _("تعديل بيانات القضية")
    STATUS_CHANGED = "status_changed", _("تغيير الحالة")
    LAWYER_ASSIGNED = "lawyer_assigned", _("إسناد المحامي المسؤول")
    LAWYER_ADDED = "lawyer_added", _("إضافة محامٍ مساند")
    LAWYER_REMOVED = "lawyer_removed", _("إزالة محامٍ مساند")
    PARTY_ADDED = "party_added", _("إضافة طرف")
    PARTY_REMOVED = "party_removed", _("إزالة طرف")
    NOTE_ADDED = "note_added", _("إضافة ملاحظة")
    CLOSED = "closed", _("إغلاق القضية")
    REOPENED = "reopened", _("إعادة فتح القضية")
    # Hearings (Phase 4) — written by hearings.services via record_case_event.
    HEARING_SCHEDULED = "hearing_scheduled", _("جدولة جلسة")
    HEARING_UPDATED = "hearing_updated", _("تعديل بيانات جلسة")
    HEARING_RESCHEDULED = "hearing_rescheduled", _("إعادة جدولة جلسة")
    HEARING_HELD = "hearing_held", _("عقد جلسة")
    HEARING_POSTPONED = "hearing_postponed", _("تأجيل جلسة")
    HEARING_CANCELLED = "hearing_cancelled", _("إلغاء جلسة")
    # Tasks + deadlines (Phase 5) — written by tasks.services via record_case_event.
    TASK_ADDED = "task_added", _("إضافة مهمة")
    TASK_STATUS_CHANGED = "task_status_changed", _("تغيير حالة مهمة")
    TASK_REMOVED = "task_removed", _("حذف مهمة")
    DEADLINE_ADDED = "deadline_added", _("إضافة موعد نهائي")
    DEADLINE_STATUS_CHANGED = "deadline_status_changed", _("تغيير حالة موعد نهائي")
    # Documents (Phase 6) — written by documents.services via record_case_event.
    DOCUMENT_ADDED = "document_added", _("إضافة مستند")
    DOCUMENT_REMOVED = "document_removed", _("سحب مستند")


class _AppendOnlyQuerySet(models.QuerySet):
    def delete(self):  # pragma: no cover - defensive
        raise PermissionError("CaseEvent rows are append-only.")

    def update(self, **kwargs):  # pragma: no cover - defensive
        raise PermissionError("CaseEvent rows are append-only.")


class CaseEvent(models.Model):
    """Human-readable case timeline (spec §26 "الخط الزمني"). Append-only; written
    by `cases.services`. Later phases (hearings, tasks, documents) emit events too."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=30, choices=CaseEventType.choices)
    summary = models.CharField(max_length=300)
    detail = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = _AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name = _("حدث في الخط الزمني")
        verbose_name_plural = _("أحداث الخط الزمني")
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=["case", "-occurred_at"])]
        default_permissions = ("add", "change", "view")

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.case.case_number}: {self.summary}"

    def delete(self, *args, **kwargs):  # pragma: no cover - defensive
        raise PermissionError("CaseEvent rows are append-only.")
