"""
Hearing — a scheduled court session for a case (spec §29–30, docs/adr/0028).

One **timezone-aware** ``scheduled_at`` is the source of truth for scheduling,
ordering and calendar bucketing (spec §29 lists `date` + `time`; the form still
splits the input, the service recombines it). A hearing is legally significant
and is **never deleted** — its lifecycle (reschedule / hold / postpone / cancel)
is status transitions only (docs/adr/0022). ``Case.next_hearing`` is *derived*
from the scheduled rows, never stored, so it can never drift (docs/adr/0028).

Visibility: a hearing is scoped through its ``Case``; v1 has no per-case siloing
(docs/adr/0008), so every authenticated staff member sees every hearing.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import AuthoredModel, TimeStampedModel
from core.querysets import ScopedManager, ScopedQuerySet


class HearingType(models.TextChoices):
    FIRST_SESSION = "first_session", _("جلسة أولى")
    PLEADING = "pleading", _("مرافعة")
    EVIDENCE = "evidence", _("بيّنات")
    DELIBERATION = "deliberation", _("مداولة")
    VERDICT = "verdict", _("نطق بالحكم")
    OTHER = "other", _("أخرى")


class HearingStatus(models.TextChoices):
    SCHEDULED = "scheduled", _("مجدولة")
    HELD = "held", _("تمت")
    POSTPONED = "postponed", _("مؤجلة")
    CANCELLED = "cancelled", _("ملغاة")


OPEN_STATUSES = {HearingStatus.SCHEDULED}
CLOSED_STATUSES = {HearingStatus.HELD, HearingStatus.POSTPONED, HearingStatus.CANCELLED}


class HearingQuerySet(ScopedQuerySet):
    def for_user(self, user) -> HearingQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        # Hearings inherit Case visibility; v1 has no per-case siloing (docs/adr/0008).
        return self.all_for_user()

    def upcoming(self) -> HearingQuerySet:
        from django.utils import timezone

        return self.filter(status=HearingStatus.SCHEDULED, scheduled_at__gte=timezone.now())

    def in_range(self, start, end) -> HearingQuerySet:
        return self.filter(scheduled_at__gte=start, scheduled_at__lt=end)

    def search(self, term: str) -> HearingQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        return self.filter(
            Q(case__case_number__icontains=term)
            | Q(case__title__icontains=term)
            | Q(court__name__icontains=term)
            | Q(room__icontains=term)
        )


class Hearing(TimeStampedModel, AuthoredModel):
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.PROTECT,  # legally significant, never deleted (docs/adr/0022)
        related_name="hearings",
        verbose_name=_("القضية"),
    )
    court = models.ForeignKey(
        "courts.Court",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hearings",
        verbose_name=_("المحكمة"),
    )
    scheduled_at = models.DateTimeField(_("موعد الجلسة"))
    hearing_type = models.CharField(
        _("نوع الجلسة"),
        max_length=20,
        choices=HearingType.choices,
        default=HearingType.FIRST_SESSION,
    )
    lawyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hearings",
        verbose_name=_("المحامي الحاضر"),
    )
    room = models.CharField(_("القاعة"), max_length=60, blank=True)
    status = models.CharField(
        _("الحالة"),
        max_length=20,
        choices=HearingStatus.choices,
        default=HearingStatus.SCHEDULED,
    )
    notes = models.TextField(_("ملاحظات"), blank=True)

    # Outcome — filled when the hearing is held / postponed / cancelled (spec §30).
    result = models.TextField(_("النتيجة"), blank=True)
    next_action = models.CharField(_("الإجراء التالي"), max_length=250, blank=True)
    next_hearing_date = models.DateField(_("تاريخ الجلسة القادمة"), null=True, blank=True)

    # The scheduled hearing this one was created as a follow-up of (postpone / hold
    # with a next date). SET_NULL so history survives if the parent is ever purged.
    previous_hearing = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="follow_ups",
        verbose_name=_("جلسة سابقة"),
    )

    objects = ScopedManager.from_queryset(HearingQuerySet)()

    class Meta:
        verbose_name = _("جلسة")
        verbose_name_plural = _("الجلسات")
        ordering = ("-scheduled_at",)
        default_permissions = ("add", "change", "view")  # never deleted (docs/adr/0022)
        indexes = [
            models.Index(fields=["case", "-scheduled_at"]),
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["scheduled_at"]),
            models.Index(fields=["court"]),
        ]

    def __str__(self) -> str:
        return f"{self.case.case_number} — {self.scheduled_at:%Y-%m-%d %H:%M}"

    @property
    def is_open(self) -> bool:
        return self.status == HearingStatus.SCHEDULED

    @property
    def is_past(self) -> bool:
        from django.utils import timezone

        return self.scheduled_at < timezone.now()
