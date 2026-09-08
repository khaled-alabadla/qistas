from __future__ import annotations

from django.contrib import admin

from clients.models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("client_number", "display_name", "type", "status", "phone", "city")
    list_filter = ("type", "status", "city")
    search_fields = ("client_number", "full_name", "company_name", "phone", "email")
    readonly_fields = ("client_number", "created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        (None, {"fields": ("client_number", "type", "status")}),
        ("الهوية", {"fields": ("full_name", "company_name", "national_id", "registration_number")}),
        ("التواصل", {"fields": ("phone", "secondary_phone", "email", "address", "city")}),
        ("أخرى", {"fields": ("notes", "created_by", "updated_by", "created_at", "updated_at")}),
    )

    def has_delete_permission(self, request, obj=None):
        # Clients are archived, not deleted (docs/adr/0022).
        return False
