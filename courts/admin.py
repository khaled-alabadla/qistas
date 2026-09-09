from __future__ import annotations

from django.contrib import admin

from courts.models import Court


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "city", "department", "phone", "is_active")
    list_filter = ("type", "is_active", "city")
    search_fields = ("name", "city", "department", "address")

    def has_delete_permission(self, request, obj=None):
        # Courts are deactivated, never deleted (docs/adr/0022).
        return False
