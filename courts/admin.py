from __future__ import annotations

from django.contrib import admin

from courts.models import Court


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "city", "is_active")
    list_filter = ("type", "is_active", "city")
    search_fields = ("name", "city")
