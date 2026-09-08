"""Function-view helpers for the capability layer (docs/adr/0007)."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.core.exceptions import PermissionDenied

from core.permissions.capabilities import can


def require_capability(capability: str) -> Callable:
    """Deny (HTTP 403) unless the user holds ``capability``.

    Assumes authentication is already enforced (LoginRequiredMiddleware).
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not can(request.user, capability):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
