"""
Tasks and deadlines (spec §31–33, docs/adr/0029).

* **`Task`** — a unit of work assigned to a person. Soft-deletable via a manual
  ``deleted_at`` (the ``cases.CaseNote`` idiom — ``SoftDeleteModel`` owns the
  default manager and cannot be a ``ScopedManager``).
* **`Deadline`** — a procedural / statutory cut-off. No assignee; *met* or
  *missed*, never hard-deleted (a missed deadline is legally significant —
  docs/adr/0022; same treatment as ``Hearing``).

"Overdue" is **computed**, never stored (docs/adr/0006): a property and a
matching queryset filter. Visibility is all-staff (docs/adr/0008) — a user's own
tasks are a *filter*, not a boundary.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import AuthoredModel, TimeStampedModel
from core.querysets import ScopedManager, ScopedQuerySet

# ── Enumerations ───────────────────────────────────────────


class TaskStatus(models.TextChoices):
    NEW = "new", _("جديدة")
    IN_PROGRESS = "in_progress", _("قيد التنفيذ")
    DONE = "done", _("مكتملة")
    CANCELLED = "cancelled", _("ملغاة")


class TaskPriority(models.TextChoices):
    LOW = "low", _("منخفضة")
    MEDIUM = "medium", _("متوسطة")
    HIGH = "high", _("عالية")
    URGENT = "urgent", _("عاجلة")


class DeadlineStatus(models.TextChoices):
    PENDING = "pending", _("معلق")
    MET = "met", _("مستوفى")
    MISSED = "missed", _("فائت")
    CANCELLED = "cancelled", _("ملغى")


# status values that make "overdue" moot
TASK_CLOSED = {TaskStatus.DONE, TaskStatus.CANCELLED}
DEADLINE_CLOSED = {DeadlineStatus.MET, DeadlineStatus.MISSED, DeadlineStatus.CANCELLED}

TASK_SEARCH_FIELDS = ("title", "description")
DEADLINE_SEARCH_FIELDS = ("title", "description")


# ── Task ───────────────────────────────────────────────────
class TaskQuerySet(ScopedQuerySet):
    def for_user(self, user) -> TaskQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        return self.all_for_user()  # all staff see all (docs/adr/0008)

    def alive(self) -> TaskQuerySet:
        return self.filter(deleted_at__isnull=True)

    def open(self) -> TaskQuerySet:
        return self.exclude(status__in=list(TASK_CLOSED))

    def overdue(self) -> TaskQuerySet:
        return self.filter(due_date__isnull=False, due_date__lt=timezone.localdate()).exclude(
            status__in=list(TASK_CLOSED)
        )

    def assigned_to(self, user) -> TaskQuerySet:
        return self.filter(assigned_to=user)

    def search(self, term: str) -> TaskQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in TASK_SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Task(TimeStampedModel, AuthoredModel):
    title = models.CharField(_("العنوان"), max_length=250)
    description = models.TextField(_("الوصف"), blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name=_("مُسندة إلى"),
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name=_("القضية"),
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name=_("الموكل"),
    )

    priority = models.CharField(
        _("الأولوية"), max_length=10, choices=TaskPriority.choices, default=TaskPriority.MEDIUM
    )
    status = models.CharField(
        _("الحالة"), max_length=15, choices=TaskStatus.choices, default=TaskStatus.NEW
    )
    due_date = models.DateField(_("تاريخ الاستحقاق"), null=True, blank=True)
    completed_at = models.DateTimeField(_("اكتملت في"), null=True, blank=True, editable=False)

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    objects = ScopedManager.from_queryset(TaskQuerySet)()

    class Meta:
        verbose_name = _("مهمة")
        verbose_name_plural = _("المهام")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["assigned_to"]),
            models.Index(fields=["case"]),
            models.Index(fields=["client"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status not in TASK_CLOSED

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_date
            and self.status not in TASK_CLOSED
            and self.due_date < timezone.localdate()
        )


# ── Deadline ───────────────────────────────────────────────
class DeadlineQuerySet(ScopedQuerySet):
    def for_user(self, user) -> DeadlineQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        return self.all_for_user()

    def open(self) -> DeadlineQuerySet:
        return self.exclude(status__in=list(DEADLINE_CLOSED))

    def overdue(self) -> DeadlineQuerySet:
        return self.filter(status=DeadlineStatus.PENDING, due_date__lt=timezone.localdate())

    def search(self, term: str) -> DeadlineQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in DEADLINE_SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Deadline(TimeStampedModel, AuthoredModel):
    title = models.CharField(_("العنوان"), max_length=250)
    description = models.TextField(_("الوصف"), blank=True)

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deadlines",
        verbose_name=_("القضية"),
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deadlines",
        verbose_name=_("الموكل"),
    )

    due_date = models.DateField(_("التاريخ النهائي"))
    status = models.CharField(
        _("الحالة"),
        max_length=15,
        choices=DeadlineStatus.choices,
        default=DeadlineStatus.PENDING,
    )
    completed_at = models.DateTimeField(_("سُجّل في"), null=True, blank=True, editable=False)

    objects = ScopedManager.from_queryset(DeadlineQuerySet)()

    class Meta:
        verbose_name = _("موعد نهائي")
        verbose_name_plural = _("المواعيد النهائية")
        ordering = ("due_date",)
        default_permissions = ("add", "change", "view")  # never deleted (docs/adr/0022)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["case"]),
            models.Index(fields=["client"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status not in DEADLINE_CLOSED

    @property
    def is_overdue(self) -> bool:
        return self.status == DeadlineStatus.PENDING and self.due_date < timezone.localdate()
