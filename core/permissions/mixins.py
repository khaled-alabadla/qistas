"""
Class-based-view mixins for authorization (docs/adr/0007, docs/adr/0019).

* ``CapabilityRequiredMixin`` — coarse, group-capability gate (403 on failure).
* ``ScopedListMixin`` / ``ScopedDetailMixin`` — force every per-object view
  through ``Model.objects.for_user(user)`` and verify it with ``assert_scoped``.
  A denied object yields **403** (docs/adr/0008 — v1 has no strict siloing, so
  404-on-forbidden would only hurt operability).
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import Http404

from core.permissions.capabilities import can
from core.querysets import assert_scoped


class CapabilityRequiredMixin:
    required_capability: str | None = None

    def get_required_capability(self) -> str:
        if not self.required_capability:
            raise ImproperlyConfigured(f"{type(self).__name__} must set `required_capability`.")
        return self.required_capability

    def dispatch(self, request, *args, **kwargs):
        if not can(request.user, self.get_required_capability()):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class _ScopedBase:
    """Shared machinery: get a queryset scoped to the current user."""

    def get_scoped_queryset(self):
        model = getattr(self, "model", None)
        queryset = getattr(self, "queryset", None)
        if model is None and queryset is not None:
            model = queryset.model
        if model is None:
            raise ImproperlyConfigured(f"{type(self).__name__} needs `model` (or `queryset`).")
        if not hasattr(model.objects, "for_user"):
            raise ImproperlyConfigured(
                f"{model.__name__}.objects must expose for_user() to use a "
                "Scoped view mixin (docs/adr/0019)."
            )
        scoped = model.objects.for_user(self.request.user)
        assert_scoped(scoped)
        return scoped


class ScopedListMixin(_ScopedBase):
    def get_queryset(self):
        return self.get_scoped_queryset()


class ScopedDetailMixin(_ScopedBase):
    def get_queryset(self):
        return self.get_scoped_queryset()

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        pk = self.kwargs.get(getattr(self, "pk_url_kwarg", "pk"))
        slug = self.kwargs.get(getattr(self, "slug_url_kwarg", "slug"))
        try:
            if pk is not None:
                return queryset.get(pk=pk)
            if slug is not None:
                slug_field = getattr(self, "slug_field", "slug")
                return queryset.get(**{slug_field: slug})
        except queryset.model.DoesNotExist:
            raise PermissionDenied from None
        raise Http404("No object identifier in URL.")
