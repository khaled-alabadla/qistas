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


@register.simple_tag
def active(request, *url_names: str, css: str = "is-active") -> str:
    """Return ``css`` when the current resolved URL name matches any given name."""
    match = getattr(request, "resolver_match", None)
    if match and match.view_name in url_names:
        return mark_safe(css)
    return ""
