"""
Document — a sensitive legal record attached to a Case and/or Client
(spec §34–36, docs/adr/0030).

Storage is private (``documents`` STORAGES entry, never web-served); the file is
only reachable through the audited download view. A document is **retired**
(soft-deleted via ``deleted_at``), never hard-deleted — the row and the blob are
retained (ADR-0022). The file itself is immutable once uploaded; metadata is
editable. Versioning is designed-for but not built (spec §36).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.querysets import ScopedManager, ScopedQuerySet
from documents.storage import document_storage, document_upload_path


class DocumentCategory(models.TextChoices):
    PLEADING = "pleading", _("لوائح ومذكرات")
    CONTRACT = "contract", _("عقد")
    POWER_OF_ATTORNEY = "power_of_attorney", _("وكالة")
    JUDGMENT = "judgment", _("حكم أو قرار")
    EVIDENCE = "evidence", _("بيّنة")
    CORRESPONDENCE = "correspondence", _("مراسلة")
    OFFICIAL = "official", _("وثيقة رسمية")
    IDENTITY = "identity", _("وثيقة هوية")
    FINANCIAL = "financial", _("مستند مالي")
    OTHER = "other", _("أخرى")


SEARCH_FIELDS = ("name", "description", "original_filename")


class DocumentQuerySet(ScopedQuerySet):
    def for_user(self, user) -> DocumentQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        return self.all_for_user()  # a case's documents follow case visibility (ADR-0008)

    def alive(self) -> DocumentQuerySet:
        return self.filter(deleted_at__isnull=True)

    def search(self, term: str) -> DocumentQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Document(TimeStampedModel):
    name = models.CharField(_("الاسم"), max_length=250)
    document_type = models.CharField(
        _("النوع"),
        max_length=30,
        choices=DocumentCategory.choices,
        default=DocumentCategory.OTHER,
    )
    description = models.TextField(_("الوصف"), blank=True)

    file = models.FileField(
        _("الملف"),
        storage=document_storage,
        upload_to=document_upload_path,
        max_length=255,
    )
    original_filename = models.CharField(_("اسم الملف الأصلي"), max_length=255, blank=True)
    content_type = models.CharField(_("نوع المحتوى"), max_length=100, blank=True, editable=False)
    size = models.PositiveBigIntegerField(_("الحجم"), default=0, editable=False)
    sha256 = models.CharField(_("بصمة SHA-256"), max_length=64, blank=True, editable=False)

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name=_("القضية"),
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name=_("الموكل"),
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
        verbose_name=_("رفعه"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    objects = ScopedManager.from_queryset(DocumentQuerySet)()

    class Meta:
        verbose_name = _("مستند")
        verbose_name_plural = _("المستندات")
        ordering = ("-created_at",)
        default_permissions = ("add", "change", "view")  # retired, never deleted
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["document_type"]),
            models.Index(fields=["case"]),
            models.Index(fields=["client"]),
            models.Index(fields=["deleted_at"]),
            models.Index(fields=["sha256"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_retired(self) -> bool:
        return self.deleted_at is not None

    @property
    def download_filename(self) -> str:
        """A safe filename for the ``Content-Disposition`` header."""
        base = (self.original_filename or self.name or "document").strip()
        base = base.replace("\r", "").replace("\n", "").replace('"', "").replace("\\", "")
        return base.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255] or "document"
