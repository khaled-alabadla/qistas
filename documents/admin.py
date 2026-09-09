from __future__ import annotations

from django.contrib import admin

from documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "document_type",
        "case",
        "client",
        "size",
        "uploaded_by",
        "created_at",
        "deleted_at",
    )
    list_filter = ("document_type",)
    search_fields = ("name", "description", "original_filename", "sha256")
    autocomplete_fields = ("case", "client")
    readonly_fields = (
        "file",
        "original_filename",
        "content_type",
        "size",
        "sha256",
        "created_at",
        "updated_at",
        "uploaded_by",
        "updated_by",
        "deleted_at",
        "deleted_by",
    )

    def has_delete_permission(self, request, obj=None):
        # Documents are retired, never hard-deleted (docs/adr/0022, 0030).
        return False
