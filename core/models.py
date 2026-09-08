"""
Abstract base models shared across apps (docs/architecture.md §4).

Phase 1 defines these; no concrete model uses `SoftDeleteModel` yet
(docs/adr/0022 — soft-delete applies to a small named set, added per phase).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("أُنشئ في"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("حُدّث في"), auto_now=True)

    class Meta:
        abstract = True


class AuthoredModel(models.Model):
    """Tracks who created / last updated a row. FKs use SET_NULL so deactivating
    a user never destroys history (docs/adr/0022)."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("أنشأه"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("آخر تعديل بواسطة"),
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=False)

    def delete(self):  # soft
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager):
    """Default manager returns only living rows; `all_with_deleted` returns everything."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(_("حُذف في"), null=True, blank=True, editable=False)

    objects = SoftDeleteManager()
    all_objects = models.Manager()  # noqa: DJ012 - intentional second manager

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):  # soft
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])
