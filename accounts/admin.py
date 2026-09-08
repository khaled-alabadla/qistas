from __future__ import annotations

import secrets

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    change_password_form = AdminPasswordChangeForm
    ordering = ("email",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "must_change_password",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("المعلومات الشخصية"), {"fields": ("first_name", "last_name", "phone", "employee_code")}),
        (
            _("الصلاحيات"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("الأمان"), {"fields": ("must_change_password",)}),
        (_("تواريخ"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )

    actions = ["issue_temp_password"]

    @admin.action(
        description=_("إصدار كلمة مرور مؤقتة (فرض التغيير عند الدخول)"),
        permissions=["issue_temp_password"],
    )
    def issue_temp_password(self, request, queryset):
        from audit.events import log_event

        count = 0
        for user in queryset:
            temp = secrets.token_urlsafe(12)
            user.set_password(temp)
            user.must_change_password = True
            user.save(update_fields=["password", "must_change_password"])
            log_event(
                request,
                action="user.temp_password_issued",
                obj=user,
                changes={"must_change_password": [False, True]},
            )
            self.message_user(
                request,
                _("كلمة مرور مؤقتة لـ %(email)s: %(temp)s") % {"email": user.email, "temp": temp},
                level=messages.WARNING,
            )
            count += 1
        self.message_user(
            request,
            ngettext("تم تحديث مستخدم واحد.", "تم تحديث %(n)d مستخدمين.", count) % {"n": count},
            level=messages.SUCCESS,
        )

    def has_issue_temp_password_permission(self, request) -> bool:
        return request.user.has_perm("accounts.issue_temp_password")
