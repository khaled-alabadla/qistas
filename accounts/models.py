"""
Custom user model (docs/adr/0004).

* `AbstractUser` subclass — keeps Django admin / permissions integration.
* Login identifier is **work email** (`USERNAME_FIELD = "email"`); `username` removed.
* `employee_code` is a nullable extension point for later (unused in v1).
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    username = None  # identifier is email
    email = models.EmailField(_("البريد الإلكتروني"), unique=True)
    phone = models.CharField(_("رقم الهاتف"), max_length=30, blank=True)
    employee_code = models.CharField(
        _("الرقم الوظيفي"),
        max_length=30,
        blank=True,
        null=True,
        unique=True,
        help_text=_("نقطة توسعة مستقبلية؛ غير مستخدم حاليًا."),
    )
    must_change_password = models.BooleanField(
        _("يجب تغيير كلمة المرور"),
        default=False,
        help_text=_("يُفرض على المستخدم تغيير كلمة المرور عند تسجيل الدخول التالي."),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("مستخدم")
        verbose_name_plural = _("المستخدمون")
        permissions = [
            ("issue_temp_password", _("إصدار كلمة مرور مؤقتة لمستخدم")),
        ]

    def __str__(self) -> str:
        full = self.get_full_name()
        return f"{full} <{self.email}>" if full else self.email

    def get_short_name(self) -> str:
        return self.first_name or self.email

    def clean(self) -> None:
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email or "").lower()

    def save(self, *args, **kwargs):
        # Normalise regardless of code path (manager, factory, admin, import).
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email).lower()
        super().save(*args, **kwargs)
