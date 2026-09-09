"""
Court — reusable reference data across cases and hearings (spec §28).

Phase 4 promotes the Phase 3 *minimal* model to the full one: it gains
``department`` / ``address`` / ``phone`` / ``notes`` and a ``ScopedQuerySet`` so
the standalone court-management UI can list / search / scope it. Courts are shared
office reference data — every staff member may view them (``courts.view``); only
the office manager edits them (``courts.manage``). A court is never deleted (it is
referenced by historical cases and hearings) — deactivation is an ``is_active``
toggle (docs/adr/0022, docs/adr/0028).
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.querysets import ScopedManager, ScopedQuerySet


class CourtType(models.TextChoices):
    CONCILIATION = "conciliation", _("صلح")
    FIRST_INSTANCE = "first_instance", _("بداية")
    APPEAL = "appeal", _("استئناف")
    CASSATION = "cassation", _("نقض")
    SHARIA = "sharia", _("شرعية")
    ADMINISTRATIVE = "administrative", _("إدارية")
    OTHER = "other", _("أخرى")


SEARCH_FIELDS = ("name", "city", "department", "address")


class CourtQuerySet(ScopedQuerySet):
    def for_user(self, user) -> CourtQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        return self.all_for_user()  # courts are shared reference data (docs/adr/0028)

    def active(self) -> CourtQuerySet:
        return self.filter(is_active=True)

    def search(self, term: str) -> CourtQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Court(models.Model):
    name = models.CharField(_("الاسم"), max_length=200)
    type = models.CharField(
        _("النوع"), max_length=30, choices=CourtType.choices, default=CourtType.FIRST_INSTANCE
    )
    city = models.CharField(_("المدينة"), max_length=80, blank=True)
    department = models.CharField(_("الدائرة"), max_length=120, blank=True)
    address = models.CharField(_("العنوان"), max_length=250, blank=True)
    phone = models.CharField(_("الهاتف"), max_length=30, blank=True)
    notes = models.TextField(_("ملاحظات"), blank=True)
    is_active = models.BooleanField(_("نشطة"), default=True)

    objects = ScopedManager.from_queryset(CourtQuerySet)()

    class Meta:
        verbose_name = _("محكمة")
        verbose_name_plural = _("المحاكم")
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["name", "city"], name="court_name_city_uniq")
        ]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.city}" if self.city else self.name
