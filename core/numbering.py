"""
Transaction-safe reference-number generation (docs/adr/0021).

Phase 1 ships the mechanism + a concurrency test. **No consumers** — the first
real use is the Clients phase.

Gaps are acceptable (docs/adr/0011): a rolled-back transaction that consumed a
number leaves a hole, and that is fine for case/client numbering.
"""

from __future__ import annotations

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


class NumberSequence(models.Model):
    """One counter row per (scope, period). Allocate inside the same transaction
    as the row you are numbering."""

    scope = models.CharField(_("النطاق"), max_length=50)
    period = models.CharField(_("الفترة"), max_length=20, blank=True, default="")
    last_value = models.PositiveBigIntegerField(_("آخر قيمة"), default=0)

    class Meta:
        verbose_name = _("تسلسل ترقيم")
        verbose_name_plural = _("تسلسلات الترقيم")
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "period"], name="numbersequence_scope_period_uniq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.scope}/{self.period or '-'} @ {self.last_value}"


@transaction.atomic
def next_number(scope: str, period: str = "") -> int:
    """Return the next integer for ``scope``/``period``, incrementing atomically.

    MUST be called within an outer transaction that also writes the numbered row,
    so a failure of that write rolls the increment back too.
    """
    row, _created = NumberSequence.objects.select_for_update().get_or_create(
        scope=scope, period=period, defaults={"last_value": 0}
    )
    row.last_value = models.F("last_value") + 1
    row.save(update_fields=["last_value"])
    row.refresh_from_db(fields=["last_value"])
    return row.last_value


def format_reference(prefix: str, value: int, *, period: str = "", width: int = 4) -> str:
    """``C``, 1, period='2026' -> ``C-2026-0001``. Western digits (docs/adr/0016)."""
    parts = [prefix]
    if period:
        parts.append(period)
    parts.append(str(value).zfill(width))
    return "-".join(parts)
