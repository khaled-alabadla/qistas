from __future__ import annotations

from django.contrib import admin

from hearings.models import Hearing


@admin.register(Hearing)
class HearingAdmin(admin.ModelAdmin):
    list_display = (
        "case",
        "scheduled_at",
        "hearing_type",
        "status",
        "court",
        "lawyer",
        "next_hearing_date",
    )
    list_filter = ("status", "hearing_type", "court")
    search_fields = ("case__case_number", "case__title", "room")
    autocomplete_fields = ("case",)
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by", "previous_hearing")
    date_hierarchy = "scheduled_at"

    def has_delete_permission(self, request, obj=None):
        # Hearings are legally significant and never deleted (docs/adr/0022).
        return False
