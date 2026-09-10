"""
Notification — one row in a user's in-app inbox (spec §45, §99, docs/adr/0035).

A notification is **personal data** and a **reference**, never a copy of domain
state:

* ``recipient`` owns the row (``CASCADE`` — it dies with the account).
* ``entity_type`` / ``entity_id`` point at the source record (like
  ``audit.AuditLog``); the live record is one click away via ``url`` and its own
  view re-checks authorization.
* ``body`` is a short server-generated Arabic sentence (§99 — "should lead to
  action"). **No sensitive figures** are stored (docs/adr/0009): an invoice
  notification carries the invoice number + due date, never the amount.
* ``dedupe_key`` + ``UniqueConstraint(recipient, dedupe_key)`` make the reminder
  scan idempotent — re-running the cron creates nothing new (docs/adr/0035 §2).

Access is *your own rows only*: ``Notification.objects.for_user(user)``
(docs/adr/0019) is the only path, and URL tampering yields **404** (strict
per-user siloing, unlike the all-staff domains).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.querysets import ScopedManager, ScopedQuerySet


class NotificationCategory(models.TextChoices):
    """The closed set of Phase 11 reminder categories (docs/adr/0035 §2)."""

    HEARING_UPCOMING = "hearing_upcoming", _("جلسة قادمة")
    TASK_OVERDUE = "task_overdue", _("مهمة متأخرة")
    DEADLINE_APPROACHING = "deadline_approaching", _("موعد نهائي يقترب")
    INVOICE_OVERDUE = "invoice_overdue", _("فاتورة متأخرة السداد")
    CONTRACT_EXPIRING = "contract_expiring", _("عقد قريب من الانتهاء")


class NotificationQuerySet(ScopedQuerySet):
    def for_user(self, user) -> NotificationQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        # Strict per-user siloing — a notification belongs to its recipient only.
        return self.filter(recipient=user)._scoped_copy()

    def unread(self) -> NotificationQuerySet:
        return self.filter(read_at__isnull=True)

    def read(self) -> NotificationQuerySet:
        return self.filter(read_at__isnull=False)


class Notification(TimeStampedModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("المستلم"),
    )
    category = models.CharField(_("الفئة"), max_length=32, choices=NotificationCategory.choices)
    title = models.CharField(_("العنوان"), max_length=150)
    body = models.CharField(_("النص"), max_length=500)
    url = models.CharField(_("الرابط"), max_length=300, blank=True)
    entity_type = models.CharField(_("نوع الكيان"), max_length=100, blank=True)
    entity_id = models.CharField(_("معرّف الكيان"), max_length=64, blank=True)
    dedupe_key = models.CharField(_("مفتاح إزالة التكرار"), max_length=200)
    read_at = models.DateTimeField(_("قُرئ في"), null=True, blank=True)

    objects = ScopedManager.from_queryset(NotificationQuerySet)()

    class Meta:
        verbose_name = _("إشعار")
        verbose_name_plural = _("الإشعارات")
        ordering = ("-created_at",)
        # No `delete` — the spec defines no delete/archive/retention (§18).
        default_permissions = ("add", "change", "view")
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"],
                name="uniq_notification_recipient_dedupe",
            ),
        ]
        indexes = [
            models.Index(fields=["recipient", "read_at"]),
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_category_display()} · {self.recipient_id} · {self.title}"

    @property
    def is_unread(self) -> bool:
        return self.read_at is None

    def mark_read(self, *, when=None) -> bool:
        """Idempotent — returns ``True`` only if this call flipped it."""
        if self.read_at is not None:
            return False
        self.read_at = when or timezone.now()
        self.save(update_fields=["read_at", "updated_at"])
        return True
