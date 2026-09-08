"""
Court — reusable across cases (spec §28).

Phase 3 ships a **minimal** model (just what a Case FK + a picker need). The full
management UI and the remaining fields (department, address, phone, notes) are
Phase 4 (docs/architecture.md §4 app roadmap).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class CourtType(models.TextChoices):
    CONCILIATION = "conciliation", _("صلح")
    FIRST_INSTANCE = "first_instance", _("بداية")
    APPEAL = "appeal", _("استئناف")
    CASSATION = "cassation", _("نقض")
    SHARIA = "sharia", _("شرعية")
    ADMINISTRATIVE = "administrative", _("إدارية")
    OTHER = "other", _("أخرى")


class Court(models.Model):
    name = models.CharField(_("الاسم"), max_length=200)
    type = models.CharField(
        _("النوع"), max_length=30, choices=CourtType.choices, default=CourtType.FIRST_INSTANCE
    )
    city = models.CharField(_("المدينة"), max_length=80, blank=True)
    is_active = models.BooleanField(_("نشطة"), default=True)

    class Meta:
        verbose_name = _("محكمة")
        verbose_name_plural = _("المحاكم")
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["name", "city"], name="court_name_city_uniq")
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.city}" if self.city else self.name
