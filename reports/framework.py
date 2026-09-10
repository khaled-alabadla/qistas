"""
Shared report primitives (docs/adr/0034).

A report **builder** returns a :class:`ReportResult` — typed columns + rows plus
optional summary metrics and **per-currency** totals (currencies are never
summed together, ADR-0032 / spec Phase 10 §10). The generic result template and
the CSV exporter both consume this one shape.

Nothing here touches the database; builders live in ``reports.selectors``.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from django.utils.formats import date_format, number_format

# Cell kinds — drive both right-alignment / rendering in the template and the
# CSV string formatting.
TEXT = "text"
NUM = "num"
MONEY = "money"
DATE = "date"
DATETIME = "datetime"
BADGE = "badge"

_NUMERIC_KINDS = {NUM, MONEY}

# A single report never materialises more than this many rows — bounds memory
# and query cost (spec Phase 10 §14). The HTML view paginates the capped list;
# the CSV writes all of it. When a query would exceed the cap the result is
# flagged ``truncated`` and the UI tells the user to narrow the filters.
MAX_ROWS = 5000

# Spreadsheet formula-injection guard (spec Phase 10 §12): a cell whose text
# starts with one of these can be interpreted as a formula by Excel / Sheets.
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_FORMULA_LEADING_CONTROL = ("\t", "\r", "\n")


@dataclass(frozen=True)
class Column:
    label: str
    kind: str = TEXT

    @property
    def numeric(self) -> bool:
        return self.kind in _NUMERIC_KINDS


@dataclass
class Cell:
    value: object = None
    kind: str = TEXT
    currency: str | None = None
    tone: str | None = None  # BADGE only: neutral / info / success / warning / danger
    href: str | None = None
    csv_override: object = None  # when the CSV value differs from the display value

    @property
    def numeric(self) -> bool:
        return self.kind in _NUMERIC_KINDS

    @property
    def display(self) -> str:
        v = self.value
        if v is None or v == "":
            return "—"
        if self.kind == MONEY:
            amount = number_format(Decimal(v), decimal_pos=2, force_grouping=True)
            return f"{amount} {self.currency}" if self.currency else amount
        if self.kind == NUM:
            if isinstance(v, (int, Decimal, float)):
                return number_format(v, force_grouping=True)
            return str(v)
        if self.kind in (DATE, DATETIME):
            fmt = "SHORT_DATE_FORMAT" if self.kind == DATE else "SHORT_DATETIME_FORMAT"
            return date_format(v, fmt) if not isinstance(v, str) else v
        return str(v)

    def csv_value(self) -> str:
        raw = self.csv_override if self.csv_override is not None else self.value
        if raw is None or raw == "":
            return ""
        if self.kind == MONEY:
            # Plain, unformatted, dot-decimal, Decimal-safe — no grouping, no
            # currency glued on (currency is its own column when it varies).
            return str(Decimal(raw))
        if self.kind == NUM:
            return str(raw)
        if self.kind == DATE and not isinstance(raw, str):
            return raw.isoformat()
        if self.kind == DATETIME and not isinstance(raw, str):
            return (
                timezone.localtime(raw).isoformat(timespec="minutes")
                if timezone.is_aware(raw)
                else raw.isoformat(timespec="minutes")
            )
        return csv_safe(str(raw))


def csv_safe(text: str) -> str:
    """Neutralise a value that a spreadsheet might read as a formula."""
    if text and (text[0] in _FORMULA_PREFIXES or text[0] in _FORMULA_LEADING_CONTROL):
        return "'" + text
    return text


@dataclass
class CurrencyTotals:
    """One block of per-currency figures. Currencies are shown side by side and
    **never added together** (ADR-0032)."""

    currency: str
    items: list[tuple[str, Decimal]]  # (label, amount)


@dataclass
class Metric:
    label: str
    value: object
    kind: str = NUM
    tone: str | None = None


@dataclass
class ReportResult:
    columns: list[Column]
    rows: list[list[Cell]] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)
    currency_totals: list[CurrencyTotals] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    truncated: bool = False
    generated_at: dt.datetime = field(default_factory=timezone.now)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def is_empty(self) -> bool:
        return not self.rows


# ── date-range helpers (spec Phase 10 §8) ──────────────────────────────────
def date_range_filter(field_name: str, date_from: dt.date | None, date_to: dt.date | None) -> dict:
    """Inclusive-on-both-ends filter for a **DateField**.

    ``date_from`` / ``date_to`` are plain dates; the row's own date field is
    compared directly (no timezone maths — a DateField has no time)."""
    flt: dict = {}
    if date_from:
        flt[f"{field_name}__gte"] = date_from
    if date_to:
        flt[f"{field_name}__lte"] = date_to
    return flt


def datetime_range_filter(
    field_name: str, date_from: dt.date | None, date_to: dt.date | None
) -> dict:
    """Inclusive-on-both-ends filter for a **DateTimeField**, evaluated in the
    active timezone: ``[from 00:00, (to + 1 day) 00:00)`` (spec Phase 10 §8 —
    never compare naive vs aware)."""
    tz = timezone.get_current_timezone()
    flt: dict = {}
    if date_from:
        flt[f"{field_name}__gte"] = timezone.make_aware(
            dt.datetime.combine(date_from, dt.time.min), tz
        )
    if date_to:
        flt[f"{field_name}__lt"] = timezone.make_aware(
            dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min), tz
        )
    return flt


def person_name(user) -> str:
    if user is None:
        return ""
    full = user.get_full_name()
    return full or user.email


# ── CSV export ────────────────────────────────────────────────────────────
def csv_response(result: ReportResult, filename: str) -> HttpResponse:
    """Render ``result``'s table (header row + data rows) as a UTF-8 CSV with a
    BOM (so Excel opens Arabic correctly). Summary metrics / per-currency totals
    stay on the HTML page — they are derivable from the columns and keeping the
    CSV a single clean table avoids ambiguous parsing."""
    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM so Excel detects the encoding for Arabic
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([csv_safe(c.label) for c in result.columns])
    for row in result.rows:
        writer.writerow([cell.csv_value() for cell in row])

    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    # Server-generated filename — never user input (spec Phase 10 §11/§12).
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
