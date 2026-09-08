"""
Object-level authorization framework (docs/adr/0019).

Phase 1 ships the machinery and its tests (against `core.tests.testapp`); real
domain models wire into it from their own phase.

Contract:
* Every model with per-object visibility exposes ``Model.objects.for_user(user)``.
* ``for_user`` is an **explicit** method — never the default manager behaviour,
  so shell / admin / imports / management commands are not silently filtered.
* Views render only scoped querysets; ``assert_scoped`` enforces this in DEBUG
  and tests, and the Scoped* view mixins call it for you.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class UnscopedQuerysetError(RuntimeError):
    """Raised when a per-object view renders a queryset that never went through
    ``for_user()``. Indicates a potential authorization bypass."""


class ScopedQuerySet(models.QuerySet):
    """Base queryset for permission-scoped models.

    Subclasses MUST override :meth:`for_user` and call :meth:`_scoped_copy` on
    the queryset they return.
    """

    _is_scoped = False

    def _clone(self, *args, **kwargs):
        clone = super()._clone(*args, **kwargs)
        clone._is_scoped = self._is_scoped
        return clone

    def _scoped_copy(self) -> ScopedQuerySet:
        clone = self._clone()
        clone._is_scoped = True
        return clone

    def for_user(self, user) -> ScopedQuerySet:
        raise NotImplementedError(
            f"{type(self).__name__} must implement for_user(user) (docs/adr/0019)."
        )

    # Helper for subclasses: managers/office-wide roles that legitimately see
    # everything still return a *scoped* queryset so the guard passes.
    def all_for_user(self) -> ScopedQuerySet:
        return self._scoped_copy()


class ScopedManager(models.Manager.from_queryset(ScopedQuerySet)):
    """Manager exposing ``for_user`` while keeping the default queryset unscoped
    (so non-request code paths are explicit about bypassing scoping)."""

    def for_user(self, user) -> ScopedQuerySet:
        return self.get_queryset().for_user(user)


def assert_scoped(queryset) -> None:
    """Raise if ``queryset`` did not pass through ``for_user()``.

    Active when ``DEBUG`` is true or ``QISTAS_ENFORCE_SCOPING`` is set (tests set
    it). Silent in production so a mistake degrades to the normal request flow
    rather than a 500 — but CI/tests will have caught it.
    """
    enforce = getattr(settings, "DEBUG", False) or getattr(
        settings, "QISTAS_ENFORCE_SCOPING", False
    )
    if not enforce:
        return
    if not getattr(queryset, "_is_scoped", False):
        raise UnscopedQuerysetError(
            f"{queryset.model.__name__} queryset was rendered without for_user() "
            "— object-level authorization may be bypassed (docs/adr/0019)."
        )
