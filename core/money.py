"""
Money primitives shared across finance-touching apps (docs/adr/0032, §42).

* `Currency` — the currencies that circulate in Palestine.
* `quantize` — the ONE rounding rule: 2 places, `ROUND_HALF_UP`. Every stored
  monetary result (line totals, subtotal, tax, total) goes through it.

Never use `float` for money. Amounts are `Decimal` end to end.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


class Currency(models.TextChoices):
    ILS = "ILS", _("شيكل")
    JOD = "JOD", _("دينار أردني")
    USD = "USD", _("دولار أمريكي")
    EUR = "EUR", _("يورو")


def quantize(value) -> Decimal:
    """Round ``value`` to 2 decimal places, half-up. Accepts anything
    ``Decimal()`` accepts; callers must never pass a ``float``."""
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)
