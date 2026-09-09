from __future__ import annotations

from django.contrib import admin

from tasks.models import Deadline, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "priority",
        "assigned_to",
        "due_date",
        "case",
        "client",
        "deleted_at",
    )
    list_filter = ("status", "priority")
    search_fields = ("title", "description", "case__case_number", "client__client_number")
    autocomplete_fields = ("case", "client")
    readonly_fields = (
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "completed_at",
        "deleted_at",
        "deleted_by",
    )

    def has_delete_permission(self, request, obj=None):
        # Tasks are soft-deleted through the service, never hard-deleted here.
        return False


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "due_date", "case", "client")
    list_filter = ("status",)
    search_fields = ("title", "description", "case__case_number")
    autocomplete_fields = ("case", "client")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by", "completed_at")

    def has_delete_permission(self, request, obj=None):
        # A missed deadline is legally significant — never deleted (docs/adr/0022).
        return False
