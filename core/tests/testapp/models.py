"""Throwaway model exercising the object-scoping framework (docs/adr/0019).

Only installed under ``config.settings.test``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.querysets import ScopedManager, ScopedQuerySet


class ScopedThingQuerySet(ScopedQuerySet):
    def for_user(self, user) -> ScopedThingQuerySet:
        if user and user.is_authenticated and user.is_superuser:
            return self.all_for_user()
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        return self.filter(owner=user)._scoped_copy()


class ScopedThing(models.Model):
    name = models.CharField(max_length=50)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scoped_things"
    )

    objects = ScopedManager.from_queryset(ScopedThingQuerySet)()

    def __str__(self) -> str:  # pragma: no cover
        return self.name
