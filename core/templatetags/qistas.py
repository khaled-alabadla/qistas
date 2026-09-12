"""Qistas template helpers: capability checks + bidi-safe numbers (docs/adr/0016, 0024)."""

from __future__ import annotations

from django import template
from django.template.defaultfilters import date as date_filter
from django.utils.formats import number_format
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.permissions.capabilities import can as _can

register = template.Library()


@register.filter(name="has_capability")
def has_capability(user, capability: str) -> bool:
    return _can(user, capability)


@register.simple_tag(takes_context=True)
def can(context, capability: str) -> bool:
    request = context.get("request")
    user = getattr(request, "user", None)
    return _can(user, capability)


@register.simple_tag
def num(value, decimals: int | None = None) -> str:
    """Render a number / identifier isolated LTR inside RTL text.

    Always Western digits. Use for case numbers, money, counts, phone numbers.
    """
    if value is None or value == "":
        return ""
    if decimals is not None:
        try:
            text = number_format(value, decimal_pos=decimals, use_l10n=True, force_grouping=True)
        except (ValueError, TypeError):
            text = str(value)
    else:
        text = str(value)
    return format_html('<bdi dir="ltr">{}</bdi>', text)


@register.simple_tag
def datestr(value, fmt: str = "SHORT_DATE_FORMAT") -> str:
    if not value:
        return ""
    return format_html('<bdi dir="ltr">{}</bdi>', date_filter(value, fmt))


@register.inclusion_tag("components/badge.html")
def badge(label, tone: str = "neutral", *, icon: str | None = None):
    return {"label": label, "tone": tone, "icon": icon}


@register.inclusion_tag("components/empty_state.html")
def empty_state(title, message: str = "", *, action_url: str | None = None, action_label: str = ""):
    return {
        "title": title,
        "message": message,
        "action_url": action_url,
        "action_label": action_label,
    }


# Restrained categorical palette shared by the donut chart and the ranked bar
# chart (dashboard/_bars.html) so the two read as one visual system.
CHART_COLORS: list[str] = [
    "#1d4ed8",  # navy
    "#b8863b",  # bronze
    "#10b981",  # emerald-500
    "#f59e0b",  # amber-500
    "#94a3b8",  # slate-400
    "#f43f5e",  # rose-500
    "#0ea5e9",  # sky-500
    "#a855f7",  # purple-500
]


@register.filter
def chart_color(index: int) -> str:
    """Look up a color from the shared CHART_COLORS palette by position."""
    return CHART_COLORS[int(index) % len(CHART_COLORS)]


@register.inclusion_tag("components/donut_chart.html")
def donut_chart(rows, size: int = 120):
    """A dependency-free SVG donut chart (spec §14 — no charting library).

    ``rows``: iterable of objects/dicts with ``label``/``value`` — same shape
    dashboard/_bars.html already consumes. Geometry uses the classic
    r=15.9155 trick (2*pi*r ≈ 100), so each segment's percentage of the
    total *is* its stroke-dasharray length, no further scaling needed.
    """
    rows = list(rows)[:8]
    total = sum(r["value"] for r in rows)
    segments = []
    cumulative = 0.0
    for i, r in enumerate(rows):
        pct = (r["value"] / total * 100) if total else 0
        segments.append(
            {
                "label": r["label"],
                "value": r["value"],
                "dasharray": f"{pct:.4f} 100",
                "dashoffset": -cumulative,
                "color": CHART_COLORS[i % len(CHART_COLORS)],
            }
        )
        cumulative += pct
    return {"segments": segments, "total": total, "size": size}


@register.simple_tag
def active(request, *url_names: str, css: str = "is-active") -> str:
    """Return ``css`` when the current resolved URL name matches any given name."""
    match = getattr(request, "resolver_match", None)
    if match and match.view_name in url_names:
        return mark_safe(css)
    return ""


# One coherent 24x24 stroke icon family (spec §11) — hand-authored, dependency-free.
_ICON_PATHS: dict[str, str] = {
    "home": (
        '<path d="M3 11.5 12 4l9 7.5"/>'
        '<path d="M5.5 10v9a1 1 0 0 0 1 1H9a1 1 0 0 0 1-1v-4h4v4a1 1 0 0 0 1 1h2.5a1 1 0 0 0 1-1'
        'v-9"/>'
    ),
    "users": (
        '<path d="M17 21v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 5 19.5V21"/>'
        '<circle cx="9.5" cy="7.5" r="3.5"/>'
        '<path d="M19 21v-1.5a3.5 3.5 0 0 0-2.5-3.35"/>'
        '<path d="M14.5 4.15a3.5 3.5 0 0 1 0 6.7"/>'
    ),
    "folder": (
        '<path d="M3 7a1 1 0 0 1 1-1h4.5l2 2H20a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>'
    ),
    "calendar": (
        '<rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9.5h18M8 3v3M16 3v3"/>'
    ),
    "chart": '<path d="M4 20V10M11 20V4M18 20v-7"/><path d="M3 20h18"/>',
    "bell": (
        '<path d="M6 9a6 6 0 1 1 12 0c0 4 1.5 5.5 2 6H4c.5-.5 2-2 2-6Z"/>'
        '<path d="M9.5 19a2.5 2.5 0 0 0 5 0"/>'
    ),
    # Simplified settings glyph (circle + 8 radial ticks) — avoids one giant gear path.
    "cog": (
        '<circle cx="12" cy="12" r="3.2"/>'
        '<path d="M12 3v2.5M12 18.5V21M21 12h-2.5M5.5 12H3'
        'M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8M18.4 18.4l-1.8-1.8M7.4 7.4 5.6 5.6"/>'
    ),
    "file-text": (
        '<path d="M7 3.5h7l4 4V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z"/>'
        '<path d="M14 3.5V8h4M9 12.5h6M9 16h6"/>'
    ),
    "wallet": (
        '<path d="M3.5 7.5A2 2 0 0 1 5.5 5.5H18a1 1 0 0 1 1 1V8"/>'
        '<path d="M3.5 7.5v10a2 2 0 0 0 2 2H19a1 1 0 0 0 1-1v-9a1 1 0 0 0-1-1H6a2.5 2.5 0 0 1 '
        '0-5h11"/><circle cx="16.2" cy="14" r="1.3"/>'
    ),
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-start": '<path d="m15 18-6-6 6-6"/>',
    "refresh": (
        '<path d="M3 12a9 9 0 0 1 15.4-6.36L21 8"/><path d="M21 3v5h-5"/>'
        '<path d="M21 12a9 9 0 0 1-15.4 6.36L3 16"/><path d="M8 21H3v-5"/>'
    ),
    "inbox": (
        '<path d="M3 12h4.5l1.5 3h6l1.5-3H21"/>'
        '<path d="M5.5 5h13l2.5 7v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z"/>'
    ),
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 5-5"/>',
    "alert-triangle": '<path d="M12 4 2.5 20.5h19Z"/><path d="M12 10v4"/><path d="M12 17.5h.01"/>',
    "x-circle": '<circle cx="12" cy="12" r="9"/><path d="m9.5 9.5 5 5m0-5-5 5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.5h.01"/>',
    "log-out": (
        '<path d="M15 4H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h9"/>'
        '<path d="M10 12h11m0 0-3.5-3.5M21 12l-3.5 3.5"/>'
    ),
}


@register.simple_tag
def icon(name: str, css: str = "h-5 w-5") -> str:
    """Render a stroke-style SVG icon from the shared Qistas icon set (spec §11)."""
    body = _ICON_PATHS.get(name, "")
    return format_html(
        '<svg class="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true">{}</svg>',
        css,
        mark_safe(body),
    )
