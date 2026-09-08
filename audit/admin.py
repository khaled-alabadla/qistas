from __future__ import annotations

from django.contrib import admin

from audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "entity_type", "entity_id", "ip_address")
    list_filter = ("action", "entity_type", "created_at")
    search_fields = ("actor__email", "object_repr", "entity_id", "ip_address")
    date_hierarchy = "created_at"
    readonly_fields = (
        "actor",
        "action",
        "entity_type",
        "entity_id",
        "object_repr",
        "changes",
        "ip_address",
        "user_agent",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
