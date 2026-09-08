from __future__ import annotations

from django.contrib import admin

from core.numbering import NumberSequence


@admin.register(NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("scope", "period", "last_value")
    list_filter = ("scope",)
    search_fields = ("scope", "period")
    readonly_fields = ("last_value",)

    def has_add_permission(self, request):
        return False
