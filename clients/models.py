"""
Client — individuals and companies the office represents (spec §20).

Authorization: every staff member may see every client (no row-level siloing in
v1 — docs/adr/0008). `national_id` / `registration_number` are gated behind
`clients.view_sensitive` (docs/adr/0009) and excluded from search + logs.
Archival is a status, never a delete (docs/adr/0022).
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import AuthoredModel, TimeStampedModel
from core.querysets import ScopedManager, ScopedQuerySet


class ClientType(models.TextChoices):
    INDIVIDUAL = "individual", _("فرد")
    COMPANY = "company", _("شركة")


class ClientStatus(models.TextChoices):
    ACTIVE = "active", _("نشط")
    INACTIVE = "inactive", _("غير نشط")
    PROSPECT = "prospect", _("عميل محتمل")
    ARCHIVED = "archived", _("مؤرشف")


# Free-text search fields (docs/adr/0009: national_id is NEVER searched).
SEARCH_FIELDS = (
    "client_number",
    "full_name",
    "company_name",
    "phone",
    "secondary_phone",
    "email",
    "city",
)


class ClientQuerySet(ScopedQuerySet):
    def for_user(self, user) -> ClientQuerySet:
        if not user or not user.is_authenticated:
            return self.none()._scoped_copy()
        # All authenticated staff see all clients (docs/adr/0008).
        return self.all_for_user()

    def active(self) -> ClientQuerySet:
        return self.exclude(status=ClientStatus.ARCHIVED)

    def search(self, term: str) -> ClientQuerySet:
        term = (term or "").strip()
        if not term:
            return self
        q = Q()
        for field in SEARCH_FIELDS:
            q |= Q(**{f"{field}__icontains": term})
        return self.filter(q)


class Client(TimeStampedModel, AuthoredModel):
    client_number = models.CharField(_("رقم العميل"), max_length=30, unique=True, editable=False)
    type = models.CharField(_("النوع"), max_length=20, choices=ClientType.choices)

    full_name = models.CharField(_("الاسم الكامل"), max_length=200, blank=True)
    company_name = models.CharField(_("اسم الشركة"), max_length=200, blank=True)

    national_id = models.CharField(_("رقم الهوية"), max_length=30, blank=True)
    registration_number = models.CharField(_("رقم التسجيل التجاري"), max_length=40, blank=True)

    phone = models.CharField(_("الهاتف"), max_length=30)
    secondary_phone = models.CharField(_("هاتف إضافي"), max_length=30, blank=True)
    email = models.EmailField(_("البريد الإلكتروني"), blank=True)
    address = models.TextField(_("العنوان"), blank=True)
    city = models.CharField(_("المدينة"), max_length=80, blank=True)

    status = models.CharField(
        _("الحالة"),
        max_length=20,
        choices=ClientStatus.choices,
        default=ClientStatus.ACTIVE,
    )
    notes = models.TextField(_("ملاحظات"), blank=True)

    objects = ScopedManager.from_queryset(ClientQuerySet)()

    class Meta:
        verbose_name = _("عميل")
        verbose_name_plural = _("العملاء")
        ordering = ("company_name", "full_name", "client_number")
        permissions = [
            ("view_sensitive_client", _("عرض بيانات العميل الحساسة (رقم الهوية)")),
        ]
        indexes = [
            models.Index(fields=["client_number"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["status"]),
            models.Index(fields=["type"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="client_name_matches_type",
                condition=(
                    Q(type=ClientType.INDIVIDUAL) & ~Q(full_name="")
                    | Q(type=ClientType.COMPANY) & ~Q(company_name="")
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.client_number})"

    @property
    def display_name(self) -> str:
        return self.company_name if self.type == ClientType.COMPANY else self.full_name

    @property
    def is_archived(self) -> bool:
        return self.status == ClientStatus.ARCHIVED

    def clean(self) -> None:
        super().clean()
        from django.core.exceptions import ValidationError

        if self.type == ClientType.INDIVIDUAL and not self.full_name.strip():
            raise ValidationError({"full_name": _("الاسم الكامل مطلوب للأفراد.")})
        if self.type == ClientType.COMPANY and not self.company_name.strip():
            raise ValidationError({"company_name": _("اسم الشركة مطلوب للشركات.")})
