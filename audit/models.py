"""
Explicit security/domain event log (spec §46, docs/adr/0020).

This is the store for **events** (login, logout, permission change, temp-password
issue, document download …). Automatic model-change diffs use django-auditlog's
own ``LogEntry`` and are wired per model from Phase 2.

`AuditLog` rows are append-only: no ORM/admin delete, `actor` is `SET_NULL`, and
a DB-level immutability trigger is added in Phase 12.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditAction(models.TextChoices):
    LOGIN = "auth.login", _("تسجيل دخول")
    LOGIN_FAILED = "auth.login_failed", _("محاولة دخول فاشلة")
    LOGOUT = "auth.logout", _("تسجيل خروج")
    LOCKOUT = "auth.lockout", _("قفل الحساب")
    PASSWORD_CHANGED = "auth.password_changed", _("تغيير كلمة المرور")
    PASSWORD_RESET = "auth.password_reset", _("إعادة تعيين كلمة المرور")
    MFA_ENABLED = "auth.mfa_enabled", _("تفعيل التحقق بخطوتين")
    MFA_DISABLED = "auth.mfa_disabled", _("إيقاف التحقق بخطوتين")
    USER_CREATED = "user.created", _("إنشاء مستخدم")
    USER_TEMP_PASSWORD = "user.temp_password_issued", _("إصدار كلمة مرور مؤقتة")
    GROUPS_CHANGED = "user.groups_changed", _("تعديل مجموعات المستخدم")
    # Clients (Phase 2)
    CLIENT_CREATED = "client.created", _("إنشاء عميل")
    CLIENT_UPDATED = "client.updated", _("تعديل بيانات عميل")
    CLIENT_ARCHIVED = "client.archived", _("أرشفة عميل")
    CLIENT_RESTORED = "client.restored", _("استعادة عميل")
    # Cases (Phase 3)
    CASE_CREATED = "case.created", _("إنشاء قضية")
    CASE_UPDATED = "case.updated", _("تعديل بيانات قضية")
    CASE_STATUS_CHANGED = "case.status_changed", _("تغيير حالة قضية")
    CASE_LAWYER_CHANGED = "case.lawyer_changed", _("تعديل محامي القضية")
    CASE_PARTY_CHANGED = "case.party_changed", _("تعديل أطراف القضية")
    CASE_NOTE_ADDED = "case.note_added", _("إضافة ملاحظة للقضية")
    CASE_CONFIDENTIAL_UPDATED = "case.confidential_updated", _("تعديل الملاحظات السرية للقضية")
    # Courts (Phase 4)
    COURT_CREATED = "court.created", _("إنشاء محكمة")
    COURT_UPDATED = "court.updated", _("تعديل بيانات محكمة")
    COURT_ACTIVATED = "court.activated", _("تفعيل محكمة")
    COURT_DEACTIVATED = "court.deactivated", _("إلغاء تفعيل محكمة")
    # Hearings (Phase 4)
    HEARING_SCHEDULED = "hearing.scheduled", _("جدولة جلسة")
    HEARING_UPDATED = "hearing.updated", _("تعديل بيانات جلسة")
    HEARING_RESCHEDULED = "hearing.rescheduled", _("إعادة جدولة جلسة")
    HEARING_HELD = "hearing.held", _("عقد جلسة")
    HEARING_POSTPONED = "hearing.postponed", _("تأجيل جلسة")
    HEARING_CANCELLED = "hearing.cancelled", _("إلغاء جلسة")
    # Tasks + deadlines (Phase 5)
    TASK_CREATED = "task.created", _("إنشاء مهمة")
    TASK_UPDATED = "task.updated", _("تعديل مهمة")
    TASK_STATUS_CHANGED = "task.status_changed", _("تغيير حالة مهمة")
    TASK_DELETED = "task.deleted", _("حذف مهمة")
    DEADLINE_CREATED = "deadline.created", _("إنشاء موعد نهائي")
    DEADLINE_UPDATED = "deadline.updated", _("تعديل موعد نهائي")
    DEADLINE_STATUS_CHANGED = "deadline.status_changed", _("تغيير حالة موعد نهائي")
    # Documents (Phase 6)
    DOCUMENT_UPLOADED = "document.uploaded", _("رفع مستند")
    DOCUMENT_UPDATED = "document.updated", _("تعديل بيانات مستند")
    DOCUMENT_DOWNLOADED = "document.downloaded", _("تنزيل مستند")
    DOCUMENT_RETIRED = "document.retired", _("سحب مستند")
    # Contracts (Phase 7)
    CONTRACT_CREATED = "contract.created", _("إنشاء عقد")
    CONTRACT_UPDATED = "contract.updated", _("تعديل بيانات عقد")
    CONTRACT_STATUS_CHANGED = "contract.status_changed", _("تغيير حالة عقد")
    OTHER = "other", _("أخرى")


class _AppendOnlyQuerySet(models.QuerySet):
    def delete(self):
        raise PermissionError("AuditLog rows are append-only (docs/adr/0020).")

    def update(self, **kwargs):
        raise PermissionError("AuditLog rows are immutable (docs/adr/0020).")

    def _raw_delete(self, using):  # pragma: no cover - defensive
        raise PermissionError("AuditLog rows are append-only (docs/adr/0020).")


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("الفاعل"),
    )
    action = models.CharField(_("الإجراء"), max_length=64)
    entity_type = models.CharField(_("نوع الكيان"), max_length=100, blank=True)
    entity_id = models.CharField(_("معرّف الكيان"), max_length=64, blank=True)
    object_repr = models.CharField(_("وصف الكيان"), max_length=200, blank=True)
    changes = models.JSONField(_("التغييرات"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("عنوان IP"), null=True, blank=True)
    user_agent = models.CharField(_("وكيل المستخدم"), max_length=300, blank=True)
    created_at = models.DateTimeField(_("حدث في"), auto_now_add=True)

    objects = _AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name = _("حدث تدقيق")
        verbose_name_plural = _("أحداث التدقيق")
        ordering = ("-created_at",)
        # No default `delete` permission — audit rows are append-only.
        default_permissions = ("add", "change", "view")
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["actor"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self) -> str:
        who = self.actor or _("مجهول")
        return f"{self.action} · {who} · {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def action_label(self) -> str:
        try:
            return AuditAction(self.action).label
        except ValueError:
            return self.action

    def delete(self, *args, **kwargs):  # pragma: no cover - defensive
        raise PermissionError("AuditLog rows are append-only (docs/adr/0020).")
