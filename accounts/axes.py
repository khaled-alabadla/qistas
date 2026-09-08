"""django-axes helpers (docs/adr/0026)."""

from __future__ import annotations


def get_username(request, credentials: dict | None = None) -> str:
    """Resolve the attempted username for lockout tracking.

    Login is by email; the form field is ``username``. Prefer the authenticate()
    credentials, fall back to POST data.
    """
    if credentials:
        value = credentials.get("username") or credentials.get("email")
        if value:
            return str(value).strip().lower()
    if request is not None:
        value = request.POST.get("username", "")
        if value:
            return value.strip().lower()
    return ""
