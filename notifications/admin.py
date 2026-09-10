from __future__ import annotations

from django.contrib import admin

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "recipient", "read_at", "created_at")
    list_filter = ("category", ("read_at", admin.EmptyFieldListFilter))
    search_fields = ("title", "body", "recipient__email", "dedupe_key")
    readonly_fields = (
        "recipient",
        "category",
        "title",
        "body",
        "url",
        "entity_type",
        "entity_id",
        "dedupe_key",
        "read_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
